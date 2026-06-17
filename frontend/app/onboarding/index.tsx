import React, { useRef, useState } from "react";
import {
  View, Text, StyleSheet, FlatList, Pressable, useWindowDimensions,
  Image, StatusBar, NativeSyntheticEvent, NativeScrollEvent,
} from "react-native";
import Animated, {
  useAnimatedStyle, useSharedValue, withTiming, interpolate, Extrapolation,
} from "react-native-reanimated";
import { LinearGradient } from "expo-linear-gradient";
import { Stack, useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { ArrowRight, ChevronRight } from "lucide-react-native";
import { useTheme } from "@/src/theme/ThemeProvider";
import { storage } from "@/src/utils/storage";
import { BullLogo } from "@/src/components/BullLogo";

type Slide = {
  id: string;
  title: string;
  subtitle: string;
  image: string;
  gradient: [string, string, string];
  accent: string;
};

const SLIDES: Slide[] = [
  {
    id: "welcome",
    title: "Welcome to My Funding Bank",
    subtitle: "Your all-in-one premium fintech super-app — bank, invest, pay, travel & protect, in one place.",
    image: "https://images.unsplash.com/photo-1659088515547-18c277330d19?w=600&q=80",
    gradient: ["#0EA5E9", "#1E40AF", "#0F172A"],
    accent: "#7DD3FC",
  },
  {
    id: "invest",
    title: "Smart Investing",
    subtitle: "Start your SIP, browse mutual funds, and let our AI coach guide you to consistent long-term wealth.",
    image: "https://images.unsplash.com/photo-1643888193686-81c45c445b95?w=600&q=80",
    gradient: ["#1E40AF", "#3B82F6", "#38BDF8"],
    accent: "#60A5FA",
  },
  {
    id: "gold",
    title: "Digital Gold Investment",
    subtitle: "Buy gold from ₹10 — 24K certified, stored in insured vaults, and redeemable anytime.",
    image: "https://images.pexels.com/photos/12920750/pexels-photo-12920750.jpeg?auto=compress&w=600&q=80",
    gradient: ["#7C2D12", "#D97706", "#FCD34D"],
    accent: "#FBBF24",
  },
  {
    id: "wallet",
    title: "Secure Wallet & Payments",
    subtitle: "UPI, QR scan, contactless payments — all bank-grade encrypted and demo-mode ready.",
    image: "https://images.unsplash.com/photo-1655807286510-a49644c29ef9?w=600&q=80",
    gradient: ["#0EA5E9", "#0284C7", "#0C4A6E"],
    accent: "#38BDF8",
  },
  {
    id: "travel",
    title: "Travel & Insurance",
    subtitle: "Book flights, hotels, buses & trains. Protect your family with Health, Life, Motor & Travel cover.",
    image: "https://images.unsplash.com/photo-1660732106134-f3009a1e90ea?w=600&q=80",
    gradient: ["#7C3AED", "#A855F7", "#EC4899"],
    accent: "#C4B5FD",
  },
  {
    id: "growth",
    title: "Financial Growth & Wealth",
    subtitle: "Earn cashback on every spend, unlock tiers, redeem points, and watch your money grow with you.",
    image: "https://images.unsplash.com/photo-1639916909400-40d53a2edd72?w=600&q=80",
    gradient: ["#065F46", "#10B981", "#34D399"],
    accent: "#6EE7B7",
  },
];

export default function Onboarding() {
  const { palette } = useTheme();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const { width } = useWindowDimensions();
  const [index, setIndex] = useState(0);
  const listRef = useRef<FlatList<Slide>>(null);
  const scrollX = useSharedValue(0);

  const onScroll = (e: NativeSyntheticEvent<NativeScrollEvent>) => {
    const x = e.nativeEvent.contentOffset.x;
    scrollX.value = x;
    const newIdx = Math.round(x / width);
    if (newIdx !== index) setIndex(newIdx);
  };

  const finishOnboarding = async () => {
    await storage.setItem("mfb_onboarded", true);
    router.replace("/(auth)/welcome");
  };

  const next = () => {
    if (index < SLIDES.length - 1) {
      const newIdx = index + 1;
      setIndex(newIdx);
      // Drive scrollX directly so reanimated worklets advance even when
      // FlatList programmatic scrolls don't emit onScroll on web.
      scrollX.value = withTiming(newIdx * width, { duration: 380 });
      listRef.current?.scrollToIndex({ index: newIdx, animated: true });
    } else {
      finishOnboarding();
    }
  };

  const skip = () => finishOnboarding();

  return (
    <View style={[s.root, { backgroundColor: palette.background }]}>
      <Stack.Screen options={{ headerShown: false }} />
      <StatusBar barStyle="light-content" />

      {/* Header: Logo + Skip */}
      <View style={[s.headerRow, { top: insets.top + 8 }]}>
        <View style={{ flexDirection: "row", alignItems: "center", gap: 8 }}>
          <BullLogo size={32} />
          <Text style={s.brandText}>My Funding Bank</Text>
        </View>
        {index < SLIDES.length - 1 ? (
          <Pressable onPress={skip} hitSlop={16} testID="onboarding-skip">
            <Text style={s.skipText}>Skip</Text>
          </Pressable>
        ) : null}
      </View>

      <FlatList
        ref={listRef}
        data={SLIDES}
        keyExtractor={(it) => it.id}
        horizontal
        pagingEnabled
        showsHorizontalScrollIndicator={false}
        onScroll={onScroll}
        scrollEventThrottle={16}
        renderItem={({ item, index: i }) => (
          <Slide
            slide={item}
            width={width}
            index={i}
            scrollX={scrollX}
          />
        )}
      />

      {/* Footer: dots + CTA */}
      <View style={[s.footer, { paddingBottom: insets.bottom + 18 }]}>
        <View style={s.dots}>
          {SLIDES.map((_, i) => (
            <Dot key={i} active={i === index} />
          ))}
        </View>

        <Pressable
          onPress={next}
          style={[s.cta, { backgroundColor: palette.primary }]}
          testID="onboarding-next"
        >
          <Text style={s.ctaText}>
            {index === SLIDES.length - 1 ? "Get Started" : "Next"}
          </Text>
          {index === SLIDES.length - 1
            ? <ArrowRight color="#fff" size={18} />
            : <ChevronRight color="#fff" size={18} />}
        </Pressable>
      </View>
    </View>
  );
}

function Slide({ slide, width, index, scrollX }: { slide: Slide; width: number; index: number; scrollX: Animated.SharedValue<number> }) {
  const insets = useSafeAreaInsets();

  // Animate slide content with parallax. On web, FlatList programmatic scroll
  // doesn't reliably emit onScroll → we drive scrollX directly from next().
  const imageStyle = useAnimatedStyle(() => {
    const inputRange = [(index - 1) * width, index * width, (index + 1) * width];
    const scale = interpolate(scrollX.value, inputRange, [0.6, 1, 0.6], Extrapolation.CLAMP);
    const opacity = interpolate(scrollX.value, inputRange, [0.4, 1, 0.4], Extrapolation.CLAMP);
    const translateY = interpolate(scrollX.value, inputRange, [50, 0, 50], Extrapolation.CLAMP);
    return { transform: [{ scale }, { translateY }], opacity };
  });

  const textStyle = useAnimatedStyle(() => {
    const inputRange = [(index - 1) * width, index * width, (index + 1) * width];
    const opacity = interpolate(scrollX.value, inputRange, [0.4, 1, 0.4], Extrapolation.CLAMP);
    const translateX = interpolate(scrollX.value, inputRange, [width * 0.2, 0, -width * 0.2], Extrapolation.CLAMP);
    return { opacity, transform: [{ translateX }] };
  });

  return (
    <View style={{ width, paddingTop: insets.top + 80, paddingHorizontal: 24, alignItems: "center" }}>
      <LinearGradient
        colors={slide.gradient as any}
        style={[s.imageGlow, { backgroundColor: slide.accent }]}
        start={{ x: 0, y: 0 }} end={{ x: 1, y: 1 }}
      >
        <Animated.View style={[{ width: "100%", height: "100%" }, imageStyle]}>
          <Image
            source={{ uri: slide.image }}
            style={{ width: "100%", height: "100%", borderRadius: 32 }}
            resizeMode="cover"
          />
        </Animated.View>
      </LinearGradient>

      <Animated.View style={[{ marginTop: 40, alignItems: "center" }, textStyle]}>
        <Text style={s.title}>{slide.title}</Text>
        <Text style={s.subtitle}>{slide.subtitle}</Text>
      </Animated.View>
    </View>
  );
}

function Dot({ active }: { active: boolean }) {
  const a = useSharedValue(active ? 1 : 0);
  React.useEffect(() => { a.value = withTiming(active ? 1 : 0, { duration: 250 }); }, [active, a]);
  const animStyle = useAnimatedStyle(() => ({
    width: interpolate(a.value, [0, 1], [8, 28]),
    backgroundColor: a.value > 0.5 ? "#38BDF8" : "#475569",
    opacity: interpolate(a.value, [0, 1], [0.5, 1]),
  }));
  return <Animated.View style={[s.dot, animStyle]} />;
}

const s = StyleSheet.create({
  root: { flex: 1 },
  headerRow: {
    position: "absolute", left: 20, right: 20,
    flexDirection: "row", justifyContent: "space-between", alignItems: "center", zIndex: 10,
  },
  brandText: { color: "#F1F5F9", fontSize: 15, fontWeight: "800" },
  skipText: { color: "#94A3B8", fontWeight: "700", fontSize: 14, padding: 6 },

  imageGlow: {
    width: 280, height: 280, borderRadius: 40, padding: 14,
    shadowColor: "#0EA5E9", shadowOpacity: 0.4, shadowRadius: 30, shadowOffset: { width: 0, height: 12 },
    elevation: 10,
  },
  title: {
    fontSize: 26, fontWeight: "800", color: "#F1F5F9",
    textAlign: "center", marginBottom: 12, letterSpacing: -0.4,
  },
  subtitle: {
    fontSize: 14, color: "#94A3B8", textAlign: "center",
    lineHeight: 22, paddingHorizontal: 8, fontWeight: "500",
  },

  footer: {
    position: "absolute", bottom: 0, left: 0, right: 0,
    paddingHorizontal: 24, gap: 18,
  },
  dots: { flexDirection: "row", justifyContent: "center", gap: 8 },
  dot: { height: 8, borderRadius: 4 },

  cta: {
    flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 8,
    paddingVertical: 16, borderRadius: 16,
  },
  ctaText: { color: "#fff", fontWeight: "800", fontSize: 16, letterSpacing: 0.2 },
});
