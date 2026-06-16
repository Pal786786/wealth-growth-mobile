import React from "react";
import { Pressable, Text, StyleSheet, ActivityIndicator, ViewStyle, View } from "react-native";
import { LinearGradient } from "expo-linear-gradient";
import { useTheme } from "@/src/theme/ThemeProvider";

type Variant = "primary" | "secondary" | "ghost" | "danger";

export function Button({
  label,
  onPress,
  variant = "primary",
  loading = false,
  disabled = false,
  testID,
  icon,
  style,
  fullWidth = true,
}: {
  label: string;
  onPress?: () => void;
  variant?: Variant;
  loading?: boolean;
  disabled?: boolean;
  testID?: string;
  icon?: React.ReactNode;
  style?: ViewStyle;
  fullWidth?: boolean;
}) {
  const { palette } = useTheme();
  const isPrimary = variant === "primary";
  const isDanger = variant === "danger";
  const isGhost = variant === "ghost";

  const content = (
    <View style={s.inner}>
      {loading ? (
        <ActivityIndicator color={isPrimary || isDanger ? "#fff" : palette.primary} />
      ) : (
        <>
          {icon}
          <Text
            style={[
              s.label,
              {
                color: isPrimary
                  ? "#FFFFFF"
                  : isDanger
                  ? "#FFFFFF"
                  : isGhost
                  ? palette.textPrimary
                  : palette.primary,
              },
            ]}
          >
            {label}
          </Text>
        </>
      )}
    </View>
  );

  return (
    <Pressable
      testID={testID}
      onPress={onPress}
      disabled={disabled || loading}
      style={({ pressed }) => [
        s.btn,
        {
          opacity: disabled ? 0.5 : pressed ? 0.85 : 1,
          transform: [{ scale: pressed ? 0.97 : 1 }],
          alignSelf: fullWidth ? "stretch" : "auto",
        },
        style,
      ]}
    >
      {isPrimary ? (
        <LinearGradient
          colors={[palette.primary, palette.secondary]}
          start={{ x: 0, y: 0 }}
          end={{ x: 1, y: 1 }}
          style={s.gradient}
        >
          {content}
        </LinearGradient>
      ) : isDanger ? (
        <View style={[s.solid, { backgroundColor: palette.danger }]}>{content}</View>
      ) : isGhost ? (
        <View style={[s.ghost, { borderColor: palette.border }]}>{content}</View>
      ) : (
        <View style={[s.solid, { backgroundColor: palette.primary + "15" }]}>{content}</View>
      )}
    </Pressable>
  );
}

const s = StyleSheet.create({
  btn: { borderRadius: 18, overflow: "hidden" },
  gradient: { paddingVertical: 16, paddingHorizontal: 20, borderRadius: 18 },
  solid: { paddingVertical: 16, paddingHorizontal: 20, borderRadius: 18 },
  ghost: { paddingVertical: 16, paddingHorizontal: 20, borderRadius: 18, borderWidth: 1 },
  inner: { flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 8 },
  label: { fontSize: 16, fontWeight: "700", letterSpacing: 0.2 },
});
