import React from "react";
import { View, Text, StyleSheet, Pressable, Share, Platform } from "react-native";
import { useRouter } from "expo-router";
import { ChevronLeft, Share2, Copy } from "lucide-react-native";
import QRCode from "react-native-qrcode-svg";
import * as Clipboard from "expo-clipboard";
import { useTheme } from "@/src/theme/ThemeProvider";
import { Screen } from "@/src/components/Screen";
import { useAuth } from "@/src/auth/AuthProvider";
import { useToast } from "@/src/components/Toast";

export default function ReceiveQR() {
  const { palette } = useTheme();
  const router = useRouter();
  const { user } = useAuth();
  const { show } = useToast();

  const upi = `${user?.mobile || "0000000000"}@mfb`;
  const payload = `upi://pay?pa=${upi}&pn=${encodeURIComponent(user?.full_name || "MFB User")}`;

  const copy = async () => {
    await Clipboard.setStringAsync(upi);
    show("success", "UPI ID copied");
  };
  const share = async () => {
    try {
      await Share.share({ message: `Pay me on My Funding Bank: ${upi}` });
    } catch {}
  };

  return (
    <Screen>
      <Pressable onPress={() => router.back()} style={s.back} testID="back-btn">
        <ChevronLeft color={palette.textPrimary} size={26} />
      </Pressable>
      <View style={s.body}>
        <Text style={[s.title, { color: palette.textPrimary }]}>Your QR Code</Text>
        <Text style={[s.subtitle, { color: palette.textSecondary }]}>Show this to receive money instantly</Text>
        <View style={[s.qrCard, { backgroundColor: "#fff", borderColor: palette.border }]}>
          <QRCode value={payload} size={220} color="#0F172A" backgroundColor="#FFFFFF" />
        </View>
        <Text style={[s.name, { color: palette.textPrimary }]}>{user?.full_name}</Text>
        <View style={[s.upiBox, { backgroundColor: palette.surface, borderColor: palette.border }]}>
          <Text style={{ color: palette.textSecondary, fontSize: 12, fontWeight: "600" }}>UPI ID</Text>
          <Text style={{ color: palette.textPrimary, fontSize: 16, fontWeight: "800", marginTop: 2 }} testID="upi-id-text">{upi}</Text>
        </View>
        <View style={s.actions}>
          <Pressable
            onPress={copy}
            style={[s.actionBtn, { backgroundColor: palette.surface, borderColor: palette.border }]}
            testID="copy-upi-btn"
          >
            <Copy color={palette.primary} size={18} />
            <Text style={{ color: palette.textPrimary, fontWeight: "700" }}>Copy UPI</Text>
          </Pressable>
          <Pressable
            onPress={share}
            style={[s.actionBtn, { backgroundColor: palette.primary }]}
            testID="share-upi-btn"
          >
            <Share2 color="#fff" size={18} />
            <Text style={{ color: "#fff", fontWeight: "700" }}>Share</Text>
          </Pressable>
        </View>
      </View>
    </Screen>
  );
}

const s = StyleSheet.create({
  back: { paddingVertical: 8 },
  body: { flex: 1, alignItems: "center", paddingTop: 8, gap: 14 },
  title: { fontSize: 24, fontWeight: "800", letterSpacing: -0.5 },
  subtitle: { fontSize: 13 },
  qrCard: { padding: 22, borderRadius: 24, marginTop: 8, borderWidth: 1 },
  name: { fontSize: 18, fontWeight: "800", marginTop: 4 },
  upiBox: { paddingVertical: 12, paddingHorizontal: 18, borderRadius: 14, borderWidth: 1, alignItems: "center" },
  actions: { flexDirection: "row", gap: 12, marginTop: 16, alignSelf: "stretch" },
  actionBtn: { flex: 1, flexDirection: "row", justifyContent: "center", alignItems: "center", gap: 8, padding: 14, borderRadius: 14, borderWidth: 1 },
});
