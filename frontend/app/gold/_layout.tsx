import { Stack } from "expo-router";
import { useTheme } from "@/src/theme/ThemeProvider";

export default function GoldLayout() {
  const { palette } = useTheme();
  return (
    <Stack
      screenOptions={{
        headerStyle: { backgroundColor: palette.background },
        headerTintColor: palette.textPrimary,
        headerTitleStyle: { fontWeight: "800" },
        contentStyle: { backgroundColor: palette.background },
      }}
    >
      <Stack.Screen name="index" options={{ headerShown: false }} />
      <Stack.Screen name="chart" options={{ title: "Live Gold Chart" }} />
      <Stack.Screen name="history" options={{ title: "Transactions" }} />
      <Stack.Screen name="analytics" options={{ title: "Gold Analytics" }} />
    </Stack>
  );
}
