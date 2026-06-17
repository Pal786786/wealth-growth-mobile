import React from "react";
import { View, StyleSheet, ViewProps } from "react-native";
import { useTheme } from "@/src/theme/ThemeProvider";
import { shadow } from "@/src/utils/shadow";

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
        },
        shadow({ color: palette.cardShadow, opacity: 1, radius: 12, offsetY: 4, elevation: 2 }),
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
  },
});
