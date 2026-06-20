import React from "react";
import { Tabs } from "expo-router";
import { Home, Wallet, TrendingUp, Plane, User, LineChart } from "lucide-react-native";
import { useTheme } from "@/src/theme/ThemeProvider";
import { FloatingTabBar } from "@/src/components/FloatingTabBar";

export default function TabsLayout() {
  const { palette } = useTheme();
  return (
    <Tabs
      tabBar={(props) => <FloatingTabBar {...props} />}
      screenOptions={{
        headerShown: false,
        tabBarActiveTintColor: palette.primary,
        tabBarInactiveTintColor: palette.textMuted,
      }}
    >
      <Tabs.Screen
        name="index"
        options={{ title: "Home", tabBarIcon: ({ color, size }) => <Home color={color} size={size} /> }}
      />
      <Tabs.Screen
        name="wallet"
        options={{ title: "Wallet", tabBarIcon: ({ color, size }) => <Wallet color={color} size={size} /> }}
      />
      <Tabs.Screen
        name="invest"
        options={{ title: "Invest", tabBarIcon: ({ color, size }) => <TrendingUp color={color} size={size} /> }}
      />
      <Tabs.Screen
        name="forex"
        options={{ title: "Forex", tabBarIcon: ({ color, size }) => <LineChart color={color} size={size} /> }}
      />
      <Tabs.Screen
        name="travel"
        options={{ title: "Travel", tabBarIcon: ({ color, size }) => <Plane color={color} size={size} /> }}
      />
      <Tabs.Screen
        name="profile"
        options={{ title: "Profile", tabBarIcon: ({ color, size }) => <User color={color} size={size} /> }}
      />
    </Tabs>
  );
}
