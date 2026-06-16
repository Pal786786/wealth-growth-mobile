import React from "react";
import { View, StyleSheet, KeyboardAvoidingView, Platform, StatusBar } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useTheme } from "@/src/theme/ThemeProvider";

export function Screen({
  children,
  scroll = false,
  padded = true,
  edges = { top: true, bottom: true },
}: {
  children: React.ReactNode;
  scroll?: boolean;
  padded?: boolean;
  edges?: { top?: boolean; bottom?: boolean };
}) {
  const { palette } = useTheme();
  const insets = useSafeAreaInsets();
  return (
    <View style={[s.root, { backgroundColor: palette.background }]}>
      <StatusBar barStyle={palette.mode === "light" ? "dark-content" : "light-content"} />
      <KeyboardAvoidingView
        behavior={Platform.OS === "ios" ? "padding" : undefined}
        style={{ flex: 1 }}
      >
        <View
          style={{
            flex: 1,
            paddingTop: edges.top ? insets.top : 0,
            paddingBottom: edges.bottom ? insets.bottom : 0,
            paddingHorizontal: padded ? 16 : 0,
          }}
        >
          {children}
        </View>
      </KeyboardAvoidingView>
    </View>
  );
}

const s = StyleSheet.create({
  root: { flex: 1 },
});
