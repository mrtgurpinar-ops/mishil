import React, { useEffect, useState } from 'react';
import { View, StyleSheet, AccessibilityInfo, Text } from 'react-native';
import Animated, {
  useSharedValue,
  useAnimatedStyle,
  withRepeat,
  withSequence,
  withTiming,
  Easing,
  interpolate,
} from 'react-native-reanimated';
import Svg, { Path, Circle, Defs, RadialGradient, Stop } from 'react-native-svg';
import { useAppStore } from '../store/useAppStore';
import { getTheme } from '../lib/theme';

interface BreathingMoonIndicatorProps {
  minutesLeft?: number;
  isSleeping?: boolean;
  size?: number;
  label?: string;
}

export const BreathingMoonIndicator: React.FC<BreathingMoonIndicatorProps> = ({
  minutesLeft = 45,
  isSleeping = false,
  size = 220,
  label,
}) => {
  const isDarkMode = useAppStore((state) => state.isDarkMode);
  const theme = getTheme(isDarkMode);
  const [reduceMotion, setReduceMotion] = useState(false);

  // Check accessibility reduce motion
  useEffect(() => {
    AccessibilityInfo.isReduceMotionEnabled().then(setReduceMotion);
    const subscription = AccessibilityInfo.addEventListener(
      'reduceMotionChanged',
      setReduceMotion
    );
    return () => {
      subscription?.remove();
    };
  }, []);

  // Shared animation values (4-second total breathing cycle: 2s inhale, 2s exhale)
  const breathAnim = useSharedValue(0);

  useEffect(() => {
    if (reduceMotion) {
      breathAnim.value = 0.5;
      return;
    }

    breathAnim.value = withRepeat(
      withSequence(
        withTiming(1, {
          duration: 2000,
          easing: Easing.inOut(Easing.sin),
        }),
        withTiming(0, {
          duration: 2000,
          easing: Easing.inOut(Easing.sin),
        })
      ),
      -1,
      true
    );
  }, [reduceMotion]);

  // Outer Aura Style
  const outerAuraStyle = useAnimatedStyle(() => {
    const scale = interpolate(breathAnim.value, [0, 1], [0.95, 1.08]);
    const opacity = interpolate(breathAnim.value, [0, 1], [0.35, 0.75]);
    return {
      transform: [{ scale }],
      opacity,
    };
  });

  // Inner Moon Core Style
  const moonCoreStyle = useAnimatedStyle(() => {
    const scale = interpolate(breathAnim.value, [0, 1], [0.98, 1.03]);
    return {
      transform: [{ scale }],
    };
  });

  // Calculate subtle warm glow if sleep time is close (<= 30 mins) or soothing purple if sleeping
  const isCloseToSleep = minutesLeft !== undefined && minutesLeft <= 30 && !isSleeping;
  const primaryGlowColor = isSleeping
    ? 'rgba(155, 89, 182, 0.35)'
    : isCloseToSleep
    ? theme.colors.accentGlow
    : theme.colors.moonBlueGlow;
  const moonColor = isSleeping
    ? '#A569BD'
    : isCloseToSleep
    ? theme.colors.accent
    : theme.colors.moonBlue;

  return (
    <View
      style={[styles.container, { width: size, height: size }]}
      accessible
      accessibilityRole="image"
      accessibilityLabel={`Bebek uyku durumu: ${label || (isSleeping ? 'Uykuda' : `${minutesLeft} dakika kaldı`)}`}
    >
      {/* Outer Breathing Aura */}
      <Animated.View
        style={[
          styles.aura,
          outerAuraStyle,
          {
            width: size * 0.95,
            height: size * 0.95,
            backgroundColor: primaryGlowColor,
            borderRadius: (size * 0.95) / 2,
          },
        ]}
      />

      {/* Secondary Soft Inner Ring */}
      <View
        style={[
          styles.innerRing,
          {
            width: size * 0.75,
            height: size * 0.75,
            borderColor: isCloseToSleep ? 'rgba(232, 168, 85, 0.15)' : 'rgba(74, 105, 189, 0.15)',
            borderRadius: (size * 0.75) / 2,
          },
        ]}
      />

      {/* Breathing Moon Core Vector */}
      <Animated.View style={[styles.moonWrapper, moonCoreStyle]}>
        <Svg width={size * 0.45} height={size * 0.45} viewBox="0 0 100 100">
          <Defs>
            <RadialGradient id="moonGlow" cx="50%" cy="50%" r="50%">
              <Stop offset="0%" stopColor={moonColor} stopOpacity="1" />
              <Stop offset="80%" stopColor={moonColor} stopOpacity="0.85" />
              <Stop offset="100%" stopColor={moonColor} stopOpacity="0.6" />
            </RadialGradient>
          </Defs>
          {/* Crescent Moon Path */}
          <Path
            d="M 50 10 A 40 40 0 1 0 90 50 A 30 30 0 1 1 50 10 Z"
            fill="url(#moonGlow)"
          />
          {/* Subtle Ambient Stars */}
          <Circle cx="80" cy="22" r="2.5" fill={isCloseToSleep ? theme.colors.accentLight : '#FFFFFF'} opacity="0.8" />
          <Circle cx="20" cy="70" r="1.5" fill="#FFFFFF" opacity="0.5" />
          <Circle cx="85" cy="65" r="2" fill={isCloseToSleep ? theme.colors.accent : '#FFFFFF'} opacity="0.6" />
        </Svg>
      </Animated.View>

      {/* Informative Overlay Text in Center/Bottom */}
      {label ? (
        <View style={styles.labelContainer}>
          <Text style={[styles.labelText, { color: theme.colors.textMuted }]}>
            {label}
          </Text>
        </View>
      ) : null}
    </View>
  );
};

const styles = StyleSheet.create({
  container: {
    alignItems: 'center',
    justifyContent: 'center',
    alignSelf: 'center',
    marginVertical: 16,
  },
  aura: {
    position: 'absolute',
  },
  innerRing: {
    position: 'absolute',
    borderWidth: 1.5,
  },
  moonWrapper: {
    alignItems: 'center',
    justifyContent: 'center',
  },
  labelContainer: {
    position: 'absolute',
    bottom: 8,
  },
  labelText: {
    fontSize: 12,
    fontFamily: 'Inter',
    fontWeight: '500',
    textAlign: 'center',
  },
});
