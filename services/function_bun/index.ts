// Mışıl Baby - High-Performance Realtime WebSocket & Edge Sync Service (Bun Runtime)
// Provides instant multi-device co-parenting synchronization for Anne, Baba, and Dadı.

const PORT = parseInt(process.env.PORT || "3000", 10);
const startTime = Date.now();

// Track connected clients per family room
const familyRooms = new Map<string, Set<any>>();

const server = Bun.serve({
  port: PORT,
  fetch(req, server) {
    const url = new URL(req.url);

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

    // 2. Realtime WebSocket Upgrade Endpoint
    if (url.pathname === "/ws") {
      const familyCode = (url.searchParams.get("family") || "GLOBAL").toUpperCase();
      const userName = url.searchParams.get("name") || "Kullanıcı";
      const userRole = url.searchParams.get("role") || "parent";

      const upgraded = server.upgrade(req, {
        data: {
          familyCode,
          userName,
          userRole,
          joinedAt: Date.now(),
        },
      });

      if (upgraded) {
        return undefined; // Handled by WebSocket
      }
      return new Response("WebSocket Upgrade Failed", { status: 400 });
    }

    // 3. HTTP Broadcast Endpoint (Called by FastAPI backend on events)
    if (url.pathname === "/api/realtime/broadcast" && req.method === "POST") {
      return (async () => {
        try {
          const body = await req.json();
          const familyCode = (body.family_code || "GLOBAL").toUpperCase();
          const eventType = body.event_type || "GENERIC_UPDATE";
          const payload = body.payload || {};

          const room = familyRooms.get(familyCode);
          let notifiedCount = 0;

          if (room) {
            const message = JSON.stringify({
              type: eventType,
              family_code: familyCode,
              payload: payload,
              timestamp: new Date().toISOString(),
            });

            for (const ws of room) {
              if (ws.readyState === 1) {
                // OPEN
                ws.send(message);
                notifiedCount++;
              }
            }
          }

          return new Response(
            JSON.stringify({
              status: "ok",
              event: eventType,
              family_code: familyCode,
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
            JSON.stringify({ status: "error", error: err.message }),
            { status: 500, headers: { "Content-Type": "application/json" } }
          );
        }
      })();
    }

    // 4. Status endpoint
    if (url.pathname === "/api/realtime/status") {
      const stats = Array.from(familyRooms.entries()).map(([code, clients]) => ({
        family_code: code,
        active_members: clients.size,
      }));

      return new Response(
        JSON.stringify({
          service: "mishil-function-bun",
          uptime: `${Math.floor((Date.now() - startTime) / 1000)}s`,
          rooms: stats,
        }),
        {
          headers: {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
          },
        }
      );
    }

    // Default 404
    return new Response(
      JSON.stringify({
        message: "Mışıl Function-Bun Realtime Relay Gateway",
        docs: "/health, /ws?family=CODE&role=mother, /api/realtime/status",
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
      const code = ws.data.familyCode;
      if (!familyRooms.has(code)) {
        familyRooms.set(code, new Set());
      }
      familyRooms.get(code)!.add(ws);

      // Broadcast join event to other family members
      const joinMsg = JSON.stringify({
        type: "MEMBER_JOINED",
        user_name: ws.data.userName,
        user_role: ws.data.userRole,
        family_code: code,
        active_clients: familyRooms.get(code)!.size,
        timestamp: new Date().toISOString(),
      });

      for (const client of familyRooms.get(code)!) {
        if (client !== ws && client.readyState === 1) {
          client.send(joinMsg);
        }
      }

      // Send welcome ACK to the joining client
      ws.send(
        JSON.stringify({
          type: "CONNECTION_ACK",
          message: `Mışıl Canlı Aile Kanalına (${code}) bağlandınız.`,
          user_role: ws.data.userRole,
          active_clients: familyRooms.get(code)!.size,
        })
      );
    },

    message(ws: any, message: any) {
      try {
        const data = typeof message === "string" ? JSON.parse(message) : message;
        const code = ws.data.familyCode;
        const room = familyRooms.get(code);

        if (room) {
          // Broadcast to all other members in the family room
          const broadcastMsg = JSON.stringify({
            ...data,
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
      } catch (err) {
        console.error("WS Message Error:", err);
      }
    },

    close(ws: any) {
      const code = ws.data.familyCode;
      const room = familyRooms.get(code);
      if (room) {
        room.delete(ws);
        if (room.size === 0) {
          familyRooms.delete(code);
        } else {
          // Broadcast leave event
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

console.log(`⚡ Mışıl Function-Bun Realtime Relay running on port ${PORT}`);
