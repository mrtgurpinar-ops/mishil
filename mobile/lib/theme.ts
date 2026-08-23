export const palette = {
  // Dark mode (Night - Primary)
  nightBackground: '#141B2E',
  nightCard: '#1D2640',
  nightCardElevated: '#242F4D',
  nightBorder: '#2A3656',
  nightText: '#C9CEDC',
  nightTextMuted: '#818B9F',
  nightHeading: '#FFFFFF',
  
  // Light mode (Day)
  dayBackground: '#F7F5F1',
  dayCard: '#FFFFFF',
  dayCardElevated: '#EDE8DF',
  dayBorder: '#E5E0D8',
  dayText: '#2A2E3D',
  dayTextMuted: '#6B7280',
  dayHeading: '#141B2E',

  // Signature Accent (Warm Honey / Amber)
  accent: '#E8A855',
  accentLight: '#F5C68A',
  accentGlow: 'rgba(232, 168, 85, 0.25)',
  accentDeep: '#C98533',

  // Status & Utility
  moonBlue: '#4A69BD',
  moonBlueGlow: 'rgba(74, 105, 189, 0.25)',
  success: '#4EBA86',
  warning: '#F39C12',
  error: '#E74C3C',
  info: '#3498DB',
};

export const typography = {
  fontFamily: {
    heading: 'Sora',
    body: 'Inter',
  },
  fontSize: {
    xs: 12,
    sm: 14,
    md: 16,
    lg: 18,
    xl: 22,
    xxl: 28,
    hero: 36,
  },
  lineHeight: {
    xs: 16,
    sm: 20,
    md: 24,
    lg: 26,
    xl: 30,
    xxl: 36,
    hero: 44,
  },
  fontWeight: {
    regular: '400' as const,
    medium: '500' as const,
    semiBold: '600' as const,
    bold: '700' as const,
  },
};

export const spacing = {
  xs: 4,
  sm: 8,
  md: 16,
  lg: 24,
  xl: 32,
  xxl: 48,
};

export const borderRadius = {
  sm: 8,
  md: 14,
  lg: 20,
  xl: 28,
  full: 9999,
};

export const getTheme = (isDark: boolean = true) => ({
  isDark,
  colors: {
    background: isDark ? palette.nightBackground : palette.dayBackground,
    card: isDark ? palette.nightCard : palette.dayCard,
    cardElevated: isDark ? palette.nightCardElevated : palette.dayCardElevated,
    border: isDark ? palette.nightBorder : palette.dayBorder,
    text: isDark ? palette.nightText : palette.dayText,
    textMuted: isDark ? palette.nightTextMuted : palette.dayTextMuted,
    heading: isDark ? palette.nightHeading : palette.dayHeading,
    accent: palette.accent,
    accentGlow: palette.accentGlow,
    accentLight: palette.accentLight,
    moonBlue: palette.moonBlue,
    moonBlueGlow: palette.moonBlueGlow,
    success: palette.success,
    warning: palette.warning,
    error: palette.error,
    info: palette.info,
  },
  typography,
  spacing,
  borderRadius,
});

export type Theme = ReturnType<typeof getTheme>;
