import React, { createContext, useCallback, useContext, useState, useRef, useEffect } from "react";
import { View, Text, StyleSheet, Animated } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useTheme } from "@/src/theme/ThemeProvider";
import { CircleCheck, CircleAlert, Info } from "lucide-react-native";
import { shadow } from "@/src/utils/shadow";

type ToastType = "success" | "error" | "info";

type Toast = { id: string; type: ToastType; message: string };

const Ctx = createContext<{ show: (type: ToastType, message: string) => void } | null>(null);

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toast, setToast] = useState<Toast | null>(null);
  const opacity = useRef(new Animated.Value(0)).current;
  const insets = useSafeAreaInsets();
  const { palette } = useTheme();
  const timeoutRef = useRef<any>(null);

  const show = useCallback((type: ToastType, message: string) => {
    if (timeoutRef.current) clearTimeout(timeoutRef.current);
    setToast({ id: Math.random().toString(36), type, message });
    Animated.timing(opacity, { toValue: 1, duration: 200, useNativeDriver: true }).start();
    timeoutRef.current = setTimeout(() => {
      Animated.timing(opacity, { toValue: 0, duration: 200, useNativeDriver: true }).start(() => {
        setToast(null);
      });
    }, 2800);
  }, [opacity]);

  useEffect(() => () => { if (timeoutRef.current) clearTimeout(timeoutRef.current); }, []);

  const color =
    toast?.type === "success" ? palette.success : toast?.type === "error" ? palette.danger : palette.primary;
  const Icon =
    toast?.type === "success" ? CircleCheck : toast?.type === "error" ? CircleAlert : Info;

  return (
    <Ctx.Provider value={{ show }}>
      {children}
      {toast ? (
        <Animated.View
          pointerEvents="none"
          style={[
            s.wrap,
            {
              top: insets.top + 12,
              backgroundColor: palette.surface,
              borderColor: palette.border,
              opacity,
            },
            shadow({ color: palette.cardShadow, opacity: 1, radius: 10, offsetY: 4, elevation: 6 }),
          ]}
        >
          <Icon color={color} size={20} />
          <Text style={[s.txt, { color: palette.textPrimary }]} numberOfLines={2}>{toast.message}</Text>
        </Animated.View>
      ) : null}
    </Ctx.Provider>
  );
}

export function useToast() {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useToast must be inside ToastProvider");
  return ctx;
}

const s = StyleSheet.create({
  wrap: {
    position: "absolute",
    left: 16,
    right: 16,
    borderRadius: 14,
    paddingVertical: 12,
    paddingHorizontal: 14,
    flexDirection: "row",
    gap: 10,
    alignItems: "center",
    borderWidth: 1,
    zIndex: 9999,
  },
  txt: { flex: 1, fontSize: 14, fontWeight: "600" },
});
