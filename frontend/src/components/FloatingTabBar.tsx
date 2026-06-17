import React from "react";
import { View, Text, StyleSheet, Pressable, Platform } from "react-native";
import { BlurView } from "expo-blur";
import { BottomTabBarProps } from "@react-navigation/bottom-tabs";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { LinearGradient } from "expo-linear-gradient";
import { useTheme } from "@/src/theme/ThemeProvider";
import { shadow } from "@/src/utils/shadow";

export function FloatingTabBar({ state, descriptors, navigation }: BottomTabBarProps) {
  const { palette } = useTheme();
  const insets = useSafeAreaInsets();
  const bottom = Math.max(insets.bottom, 12);
  const isDark = palette.mode === "dark";

  return (
    <View pointerEvents="box-none" style={[s.host, { bottom }]}>
      <View
        style={[
          s.barShell,
          {
            backgroundColor: isDark ? "rgba(15,23,42,0.92)" : "rgba(255,255,255,0.92)",
            borderColor: isDark ? "#1E293B" : "rgba(226,232,240,0.9)",
          },
          shadow({
            color: isDark ? "#000" : palette.brand?.primary || "#38BDF8",
            opacity: 0.22, radius: 16, offsetY: 8, elevation: 12,
          }),
        ]}
      >
        {Platform.OS !== "web" ? (
          <BlurView
            intensity={isDark ? 40 : 60}
            tint={isDark ? "dark" : "light"}
            style={StyleSheet.absoluteFill}
          />
        ) : null}
        <View style={s.row}>
          {state.routes.map((route, index) => {
            const { options } = descriptors[route.key];
            const focused = state.index === index;
            const Icon = (options as any).tabBarIcon;
            const onPress = () => {
              const event = navigation.emit({ type: "tabPress", target: route.key, canPreventDefault: true });
              if (!focused && !event.defaultPrevented) navigation.navigate(route.name as any);
            };
            return (
              <Pressable
                key={route.key}
                onPress={onPress}
                style={s.tab}
                testID={`tab-${route.name}`}
              >
                <View style={s.tabInner}>
                  {focused ? (
                    <LinearGradient
                      colors={["#38BDF8", "#0EA5E9"]}
                      style={s.activePill}
                      start={{ x: 0, y: 0 }} end={{ x: 1, y: 1 }}
                    >
                      {Icon ? <Icon color="#FFFFFF" size={20} focused /> : null}
                      <Text style={s.activeLabel} numberOfLines={1}>{options.title || route.name}</Text>
                    </LinearGradient>
                  ) : (
                    <>
                      {Icon ? <Icon color={palette.textMuted} size={22} focused={false} /> : null}
                    </>
                  )}
                </View>
              </Pressable>
            );
          })}
        </View>
      </View>
    </View>
  );
}

const s = StyleSheet.create({
  host: { position: "absolute", left: 16, right: 16 },
  barShell: {
    borderRadius: 28,
    overflow: "hidden",
    borderWidth: 1,
  },
  row: { flexDirection: "row", alignItems: "center", paddingHorizontal: 8, paddingVertical: 8 },
  tab: { flex: 1, alignItems: "center" },
  tabInner: { alignItems: "center", justifyContent: "center", minHeight: 42 },
  activePill: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
    paddingHorizontal: 14,
    paddingVertical: 10,
    borderRadius: 20,
  },
  activeLabel: { color: "#FFFFFF", fontSize: 12, fontWeight: "800", letterSpacing: 0.2 },
});
