import React, { useEffect, useState } from "react";
import { Modal, View, Text, StyleSheet, Pressable, DeviceEventEmitter, Animated, Easing } from "react-native";
import { useRouter } from "expo-router";
import { LinearGradient } from "expo-linear-gradient";
import { Colors } from "@/src/theme/colors";
import { KYC_REQUIRED_EVENT, type KycRequiredPayload } from "@/src/api/kycGate";
import { Shield, ArrowRight, X, Lock } from "lucide-react-native";

export default function KycRequiredModal() {
  const router = useRouter();
  const [visible, setVisible] = useState(false);
  const [payload, setPayload] = useState<KycRequiredPayload | null>(null);
  const scale = React.useRef(new Animated.Value(0.8)).current;

  useEffect(() => {
    const sub = DeviceEventEmitter.addListener(KYC_REQUIRED_EVENT, (p: KycRequiredPayload) => {
      setPayload(p);
      setVisible(true);
      Animated.timing(scale, { toValue: 1, duration: 320, easing: Easing.out(Easing.back(1.4)), useNativeDriver: true }).start();
    });
    return () => sub.remove();
  }, [scale]);

  const dismiss = () => { setVisible(false); scale.setValue(0.8); };

  const goToKyc = () => {
    dismiss();
    router.push("/kyc");
  };

  return (
    <Modal transparent visible={visible} animationType="fade" onRequestClose={dismiss} statusBarTranslucent>
      <View style={styles.backdrop}>
        <Animated.View style={[styles.card, { transform: [{ scale }] }]}>
          <LinearGradient colors={["#0F172A", "#1E293B"]} start={{x:0,y:0}} end={{x:1,y:1}} style={styles.header}>
            <View style={styles.iconWrap}>
              <LinearGradient colors={["#F0CC5C", "#D4AF37", "#8E700F"]} style={styles.iconBg}>
                <Shield color="#0F172A" size={28} strokeWidth={2.5} />
              </LinearGradient>
            </View>
            <Pressable onPress={dismiss} style={styles.closeBtn} hitSlop={12}>
              <X color="#94A3B8" size={18} />
            </Pressable>
            <Text style={styles.title}>KYC Verification Required</Text>
            <Text style={styles.eyebrow}>SECURITY & COMPLIANCE</Text>
          </LinearGradient>

          <View style={styles.body}>
            <Text style={styles.msg}>
              Complete your KYC to unlock{"\n"}
              <Text style={styles.msgBold}>Wallet, Investments, Gold & Forex.</Text>
            </Text>
            <View style={styles.lockRow}>
              <Lock color="#94A3B8" size={14} />
              <Text style={styles.lockText}>{payload?.message || "KYC verification required before using this service."}</Text>
            </View>
            <Pressable onPress={goToKyc} style={({ pressed }) => [styles.cta, pressed && { opacity: 0.9 }]}>
              <LinearGradient colors={["#F0CC5C", "#D4AF37", "#B8941F"]} start={{x:0,y:0}} end={{x:1,y:0}} style={styles.ctaGrad}>
                <Text style={styles.ctaText}>Complete KYC</Text>
                <ArrowRight color="#0F172A" size={18} strokeWidth={2.5} />
              </LinearGradient>
            </Pressable>
            <Pressable onPress={dismiss}><Text style={styles.later}>Maybe later</Text></Pressable>
          </View>
        </Animated.View>
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  backdrop: { flex: 1, backgroundColor: "rgba(0,0,0,0.7)", justifyContent: "center", alignItems: "center", padding: 24 },
  card: { width: "100%", maxWidth: 380, borderRadius: 24, overflow: "hidden", backgroundColor: "#FFF", elevation: 12, shadowColor: "#000", shadowOpacity: 0.3, shadowRadius: 24, shadowOffset: { width: 0, height: 12 } },
  header: { paddingTop: 32, paddingBottom: 24, paddingHorizontal: 24, alignItems: "center", position: "relative" },
  iconWrap: { marginBottom: 12 },
  iconBg: { width: 64, height: 64, borderRadius: 20, alignItems: "center", justifyContent: "center", shadowColor: "#D4AF37", shadowOpacity: 0.5, shadowRadius: 12, elevation: 6 },
  closeBtn: { position: "absolute", top: 14, right: 14, padding: 8 },
  eyebrow: { color: "#D4AF37", fontSize: 10, fontWeight: "800", letterSpacing: 2, marginTop: 4 },
  title: { color: "#F8FAFC", fontSize: 20, fontWeight: "800", marginTop: 4 },
  body: { padding: 24 },
  msg: { color: "#334155", fontSize: 15, textAlign: "center", lineHeight: 22 },
  msgBold: { color: "#0F172A", fontWeight: "800" },
  lockRow: { flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 6, marginVertical: 16, backgroundColor: "#F1F5F9", padding: 10, borderRadius: 10 },
  lockText: { color: "#64748B", fontSize: 11, flexShrink: 1 },
  cta: { borderRadius: 14, overflow: "hidden", marginTop: 4 },
  ctaGrad: { flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 8, paddingVertical: 14 },
  ctaText: { color: "#0F172A", fontSize: 15, fontWeight: "800" },
  later: { color: "#94A3B8", fontSize: 13, textAlign: "center", marginTop: 14, paddingVertical: 8 },
});
