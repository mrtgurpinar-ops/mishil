import React from 'react';
import { View, StyleSheet, ViewStyle } from 'react-native';
import { useAppStore } from '../../store/useAppStore';
import { getTheme } from '../../lib/theme';

interface CardProps {
  children: React.ReactNode;
  style?: ViewStyle;
  elevated?: boolean;
  bordered?: boolean;
}

export const Card: React.FC<CardProps> = ({
  children,
  style,
  elevated = false,
  bordered = true,
}) => {
  const isDarkMode = useAppStore((state) => state.isDarkMode);
  const theme = getTheme(isDarkMode);

  return (
    <View
      style={[
        styles.card,
        {
          backgroundColor: elevated ? theme.colors.cardElevated : theme.colors.card,
          borderColor: bordered ? theme.colors.border : 'transparent',
          borderWidth: bordered ? 1 : 0,
          borderRadius: theme.borderRadius.lg,
          padding: theme.spacing.md,
        },
        style,
      ]}
    >
      {children}
    </View>
  );
};

const styles = StyleSheet.create({
  card: {
    marginVertical: 6,
  },
});
