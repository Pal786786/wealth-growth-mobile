import React from "react";
import { View, StyleSheet, ViewProps } from "react-native";
import { useTheme } from "@/src/theme/ThemeProvider";

export function Card({ children, style, ...rest }: ViewProps) {
  const { palette } = useTheme();
  return (
    <View
      {...rest}
      style={[
        s.card,
        {
          backgroundColor: palette.surface,
          borderColor: palette.border,
          shadowColor: palette.cardShadow,
        },
        style,
      ]}
    >
      {children}
    </View>
  );
}

const s = StyleSheet.create({
  card: {
    borderRadius: 20,
    padding: 16,
    borderWidth: 1,
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 1,
    shadowRadius: 12,
    elevation: 2,
  },
});
