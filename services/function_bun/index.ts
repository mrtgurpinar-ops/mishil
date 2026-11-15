// Mışıl Baby — Hardened Realtime WebSocket & Edge Sync Service (Bun Runtime, v4.52.0)
// Enforces HMAC-SHA256 signed `realtime_token` room isolation (rm_*) for up to 3 co-parents.

import { createHmac, timingSafeEqual } from "node:crypto";

const PORT = parseInt(process.env.PORT || "3000", 10);
const startTime = Date.now();

const DEFAULT_DEV_SECRET = "mishil_default_dev_jwt_secret_key_change_in_production_32_bytes";
const IS_PRODUCTION =
  (process.env.ENVIRONMENT || "").trim().toLowerCase() === "production" ||
  (process.env.NODE_ENV || "").trim().toLowerCase() === "production" ||
  Boolean(process.env.RAILWAY_ENVIRONMENT);

const RAW_CONFIGURED_SECRET = (process.env.RELAY_HMAC_SECRET || process.env.JWT_SECRET || "").trim();
if (IS_PRODUCTION && (!RAW_CONFIGURED_SECRET || RAW_CONFIGURED_SECRET === DEFAULT_DEV_SECRET)) {
  throw new Error(
    "FATAL SECURITY ERROR: RELAY_HMAC_SECRET or a strong non-default JWT_SECRET must be set in production."
  );
}

const RELAY_SECRET = RAW_CONFIGURED_SECRET || DEFAULT_DEV_SECRET;

const MAX_WS_MESSAGE_BYTES = 8192;
const MAX_HTTP_RELAY_BYTES = 8192;
const ALLOWED_WS_EVENT_TYPES = new Set([
  "SLEEP_STARTED",
  "SLEEP_COMPLETED",
  "LEAP_OVERRIDE",
  "PROFILE_UPDATED",
  "ROUTINE_UPDATED",
  "FAMILY_SYNC_UPDATED",
  "PARTNER_WHISPER",
  "PING",
]);

interface VerifiedRoomClaims {
  rk: string;
  role: string;
  name: string;
  exp: number;
}

function constantTimeHexEqual(a: string, b: string): boolean {
  const cleanA = (a || "").trim().toLowerCase();
  const cleanB = (b || "").trim().toLowerCase();
  if (!cleanA || cleanA.length !== cleanB.length) return false;
  try {
    return timingSafeEqual(Buffer.from(cleanA, "utf8"), Buffer.from(cleanB, "utf8"));
  } catch {
    return false;
  }
}

function constantTimeSecretEqual(a: string, b: string): boolean {
  const bufA = Buffer.from(a || "", "utf8");
  const bufB = Buffer.from(b || "", "utf8");
  if (bufA.length === 0 || bufA.length !== bufB.length) return false;
  return timingSafeEqual(bufA, bufB);
}

function verifyRealtimeToken(rawToken: string | null): VerifiedRoomClaims | null {
  if (!rawToken || !rawToken.includes(".")) return null;
  const dotIdx = rawToken.indexOf(".");
  const payloadB64 = rawToken.slice(0, dotIdx).trim();
  const sigHex = rawToken.slice(dotIdx + 1).trim();
  if (!payloadB64 || !sigHex) return null;

  const expectedSig = createHmac("sha256", RELAY_SECRET)
    .update(payloadB64, "ascii")
    .digest("hex");

  if (!constantTimeHexEqual(sigHex, expectedSig)) return null;

  try {
    const padLen = (4 - (payloadB64.length % 4)) % 4;
    const padded = payloadB64.replace(/-/g, "+").replace(/_/g, "/") + "=".repeat(padLen);
    const decodedJson = Buffer.from(padded, "base64").toString("utf8");
    const parsed = JSON.parse(decodedJson);
    const nowSec = Math.floor(Date.now() / 1000);
    if (!parsed || typeof parsed.rk !== "string" || !parsed.rk.startsWith("rm_")) {
      return null;
    }
    if (typeof parsed.exp !== "number" || parsed.exp < nowSec) {
      return null;
    }
    return {
      rk: parsed.rk.slice(0, 64),
      role: typeof parsed.role === "string" ? parsed.role.slice(0, 24) : "mother",
      name: typeof parsed.name === "string" ? parsed.name.slice(0, 40) : "Ebeveyn",
      exp: parsed.exp,
    };
  } catch {
    return null;
  }
}

// Track connected clients per internal room_key (never public invite_code)
const familyRooms = new Map<string, Set<any>>();

const server = Bun.serve({
  port: PORT,
  fetch(req, server) {
    const url = new URL(req.url);

    if (req.method === "OPTIONS") {
      return new Response(null, {
        status: 204,
        headers: {
          "Access-Control-Allow-Origin": "*",
          "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
          "Access-Control-Allow-Headers": "Content-Type, X-Mishil-Relay-Secret",
        },
      });
    }

    // 1. Health Probe for Railway
    if (url.pathname === "/health" || url.pathname === "/healthz") {
      return new Response(
        JSON.stringify({
          status: "ok",
          service: "mishil-function-bun",
          runtime: "Bun " + Bun.version,
          uptime_sec: Math.floor((Date.now() - startTime) / 1000),
          active_rooms: familyRooms.size,
        }),
        {
          headers: {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
          },
        }
      );
    }

    // 2. Authenticated Realtime WebSocket Upgrade Endpoint
    if (url.pathname === "/ws") {
      const token = url.searchParams.get("token");
      const claims = verifyRealtimeToken(token);
      if (!claims) {
        return new Response(
          JSON.stringify({ status: "error", detail: "Unauthorized: valid realtime_token required." }),
          { status: 401, headers: { "Content-Type": "application/json" } }
        );
      }

      const upgraded = server.upgrade(req, {
        data: {
          roomKey: claims.rk,
          userName: claims.name,
          userRole: claims.role,
          joinedAt: Date.now(),
        },
      });

      if (upgraded) {
        return undefined;
      }
      return new Response("WebSocket Upgrade Failed", { status: 400 });
    }

    // 3. Authenticated HTTP Broadcast Endpoint (Called by FastAPI backend on family events)
    if (url.pathname === "/api/realtime/broadcast" && req.method === "POST") {
      const providedSecret = req.headers.get("x-mishil-relay-secret") || "";
      if (!constantTimeSecretEqual(providedSecret, RELAY_SECRET)) {
        return new Response(
          JSON.stringify({ status: "error", detail: "Unauthorized relay secret." }),
          { status: 401, headers: { "Content-Type": "application/json" } }
        );
      }

      const declaredLen = parseInt(req.headers.get("content-length") || "0", 10);
      if (Number.isFinite(declaredLen) && declaredLen > MAX_HTTP_RELAY_BYTES) {
        return new Response(
          JSON.stringify({ status: "error", detail: "Payload exceeds 8192-byte limit." }),
          { status: 413, headers: { "Content-Type": "application/json" } }
        );
      }

      return (async () => {
        try {
          const rawBody = await req.text();
          if (Buffer.byteLength(rawBody, "utf8") > MAX_HTTP_RELAY_BYTES) {
            return new Response(
              JSON.stringify({ status: "error", detail: "Payload exceeds 8192-byte limit." }),
              { status: 413, headers: { "Content-Type": "application/json" } }
            );
          }
          const body = JSON.parse(rawBody);
          const roomKey = String(body.room_key || "").trim();
          const eventType = String(body.event_type || "FAMILY_SYNC_UPDATED").trim();
          if (!roomKey.startsWith("rm_") || !ALLOWED_WS_EVENT_TYPES.has(eventType)) {
            return new Response(
              JSON.stringify({ status: "error", detail: "Invalid room_key or event_type." }),
              { status: 400, headers: { "Content-Type": "application/json" } }
            );
          }

          const room = familyRooms.get(roomKey);
          let notifiedCount = 0;

          if (room) {
            const message = JSON.stringify({
              type: eventType,
              payload: body.payload || {},
              timestamp: new Date().toISOString(),
            });

            for (const ws of room) {
              if (ws.readyState === 1) {
                ws.send(message);
                notifiedCount++;
              }
            }
          }

          return new Response(
            JSON.stringify({
              status: "ok",
              event: eventType,
              clients_notified: notifiedCount,
            }),
            {
              headers: {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*",
              },
            }
          );
        } catch (err: any) {
          return new Response(
            JSON.stringify({ status: "error", error: "Invalid JSON payload." }),
            { status: 400, headers: { "Content-Type": "application/json" } }
          );
        }
      })();
    }

    // 4. Redacted Status Endpoint (NEVER exposes room keys or invite codes)
    if (url.pathname === "/api/realtime/status") {
      let connectedClients = 0;
      for (const clients of familyRooms.values()) {
        connectedClients += clients.size;
      }

      return new Response(
        JSON.stringify({
          status: "ok",
          service: "mishil-function-bun",
          uptime: `${Math.floor((Date.now() - startTime) / 1000)}s`,
          active_rooms: familyRooms.size,
          connected_clients: connectedClients,
        }),
        {
          headers: {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
          },
        }
      );
    }

    return new Response(
      JSON.stringify({
        message: "Mışıl Function-Bun Authenticated Realtime Relay Gateway",
        docs: "/health, /ws?token=SIGNED_TOKEN, /api/realtime/status",
      }),
      {
        status: 200,
        headers: {
          "Content-Type": "application/json",
          "Access-Control-Allow-Origin": "*",
        },
      }
    );
  },

  websocket: {
    open(ws: any) {
      const rk = ws.data.roomKey;
      if (!familyRooms.has(rk)) {
        familyRooms.set(rk, new Set());
      }
      familyRooms.get(rk)!.add(ws);

      const joinMsg = JSON.stringify({
        type: "MEMBER_JOINED",
        user_name: ws.data.userName,
        user_role: ws.data.userRole,
        active_clients: familyRooms.get(rk)!.size,
        timestamp: new Date().toISOString(),
      });

      for (const client of familyRooms.get(rk)!) {
        if (client !== ws && client.readyState === 1) {
          client.send(joinMsg);
        }
      }

      ws.send(
        JSON.stringify({
          type: "CONNECTION_ACK",
          user_role: ws.data.userRole,
          active_clients: familyRooms.get(rk)!.size,
        })
      );
    },

    message(ws: any, message: any) {
      try {
        const rawStr = typeof message === "string" ? message : Buffer.from(message).toString("utf8");
        if (Buffer.byteLength(rawStr, "utf8") > MAX_WS_MESSAGE_BYTES) {
          return;
        }
        const data = JSON.parse(rawStr);
        if (!data || typeof data.type !== "string" || !ALLOWED_WS_EVENT_TYPES.has(data.type)) {
          return;
        }
        if (data.type === "PING") {
          ws.send(JSON.stringify({ type: "PONG", timestamp: new Date().toISOString() }));
          return;
        }

        const rk = ws.data.roomKey;
        const room = familyRooms.get(rk);

        if (room) {
          const broadcastMsg = JSON.stringify({
            type: data.type,
            payload: typeof data.payload === "object" && data.payload !== null ? data.payload : {},
            duration_min: typeof data.duration_min === "number" ? data.duration_min : undefined,
            leap: typeof data.leap === "number" || data.leap === null ? data.leap : undefined,
            sender_name: ws.data.userName,
            sender_role: ws.data.userRole,
            timestamp: new Date().toISOString(),
          });

          for (const client of room) {
            if (client !== ws && client.readyState === 1) {
              client.send(broadcastMsg);
            }
          }
        }
      } catch {
        // Ignore malformed WS JSON frames cleanly
      }
    },

    close(ws: any) {
      const rk = ws.data.roomKey;
      const room = familyRooms.get(rk);
      if (room) {
        room.delete(ws);
        if (room.size === 0) {
          familyRooms.delete(rk);
        } else {
          const leaveMsg = JSON.stringify({
            type: "MEMBER_LEFT",
            user_name: ws.data.userName,
            user_role: ws.data.userRole,
            active_clients: room.size,
          });
          for (const client of room) {
            if (client.readyState === 1) client.send(leaveMsg);
          }
        }
      }
    },
  },
});

console.log(`⚡ Mışıl Function-Bun Authenticated Realtime Relay running on port ${PORT}`);
