import { Stack } from "expo-router";
import { useTheme } from "@/src/theme/ThemeProvider";

export default function MFLayout() {
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
      <Stack.Screen name="explore" options={{ title: "Explore Funds" }} />
      <Stack.Screen name="fund/[id]" options={{ title: "Fund Details" }} />
      <Stack.Screen name="portfolio" options={{ title: "MF Portfolio" }} />
      <Stack.Screen name="sips" options={{ title: "My SIPs" }} />
      <Stack.Screen name="goals" options={{ title: "Goals" }} />
      <Stack.Screen name="compare" options={{ title: "Compare Funds" }} />
      <Stack.Screen name="watchlist" options={{ title: "Watchlist" }} />
      <Stack.Screen name="advisor" options={{ title: "AI MF Advisor" }} />
      <Stack.Screen name="orders" options={{ title: "Order History" }} />
    </Stack>
  );
}
