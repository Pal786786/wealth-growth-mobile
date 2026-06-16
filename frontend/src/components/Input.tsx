import React from "react";
import { TextInput, View, Text, StyleSheet, TextInputProps } from "react-native";
import { useTheme } from "@/src/theme/ThemeProvider";

type Props = TextInputProps & {
  label?: string;
  error?: string;
  leftIcon?: React.ReactNode;
  rightSlot?: React.ReactNode;
  testID?: string;
};

export function Input({ label, error, leftIcon, rightSlot, style, testID, ...rest }: Props) {
  const { palette } = useTheme();
  return (
    <View style={s.wrap}>
      {label ? <Text style={[s.label, { color: palette.textSecondary }]}>{label}</Text> : null}
      <View
        style={[
          s.inputWrap,
          {
            backgroundColor: palette.mode === "light" ? palette.surfaceAlt : palette.surface,
            borderColor: error ? palette.danger : palette.border,
          },
        ]}
      >
        {leftIcon ? <View style={s.icon}>{leftIcon}</View> : null}
        <TextInput
          testID={testID}
          placeholderTextColor={palette.textMuted}
          style={[s.input, { color: palette.textPrimary }, style]}
          {...rest}
        />
        {rightSlot ? <View style={s.icon}>{rightSlot}</View> : null}
      </View>
      {error ? <Text style={[s.error, { color: palette.danger }]}>{error}</Text> : null}
    </View>
  );
}

const s = StyleSheet.create({
  wrap: { gap: 6 },
  label: { fontSize: 13, fontWeight: "600", letterSpacing: 0.3 },
  inputWrap: {
    flexDirection: "row",
    alignItems: "center",
    borderRadius: 14,
    borderWidth: 1,
    paddingHorizontal: 14,
    minHeight: 52,
  },
  input: { flex: 1, fontSize: 16, paddingVertical: 14 },
  icon: { marginHorizontal: 4 },
  error: { fontSize: 12, marginLeft: 4 },
});
