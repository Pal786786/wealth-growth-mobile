import React, { useEffect, useState } from "react";
import {
  View, Text, StyleSheet, ActivityIndicator, ScrollView, TouchableOpacity, Share, Image,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import { useRouter } from "expo-router";
import { rewardsApi } from "@/src/api/rewards";

export default function RewardsReferrals() {
  const router = useRouter();
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => { rewardsApi.referrals().then(setData).catch(() => {}).finally(() => setLoading(false)); }, []);

  if (loading) return (
    <SafeAreaView style={styles.center}><ActivityIndicator size="large" color="#FFB100" /></SafeAreaView>
  );

  const share = async () => {
    try {
      await Share.share({
        message: `Join My Funding Bank with my code ${data.code}! ${data.link}`,
      });
    } catch {}
  };

  return (
    <SafeAreaView style={styles.safe}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.back()}><Ionicons name="chevron-back" size={24} color="#EAEAF0" /></TouchableOpacity>
        <Text style={styles.title}>Refer & Earn</Text>
        <View style={{ width: 24 }} />
      </View>

      <ScrollView contentContainerStyle={{ padding: 16 }}>
        <View style={styles.card}>
          <Text style={styles.codeLabel}>YOUR REFERRAL CODE</Text>
          <Text style={styles.code}>{data.code}</Text>
          <Image
            source={{ uri: `data:image/png;base64,${data.qr_png_base64}` }}
            style={styles.qr}
            resizeMode="contain"
          />
          <Text style={styles.link}>{data.link}</Text>
          <TouchableOpacity style={styles.shareBtn} onPress={share}>
            <Ionicons name="share-outline" size={18} color="#0E0F14" />
            <Text style={styles.shareTxt}>Share Invite</Text>
          </TouchableOpacity>
        </View>

        <View style={styles.statsRow}>
          <View style={styles.statCard}><Text style={styles.statVal}>{data.totals.installed}</Text><Text style={styles.statLbl}>Installed</Text></View>
          <View style={styles.statCard}><Text style={styles.statVal}>{data.totals.registered}</Text><Text style={styles.statLbl}>Registered</Text></View>
          <View style={styles.statCard}><Text style={styles.statVal}>{data.totals.kyc_completed}</Text><Text style={styles.statLbl}>KYC</Text></View>
          <View style={styles.statCard}><Text style={styles.statVal}>{data.totals.first_deposit}</Text><Text style={styles.statLbl}>Deposit</Text></View>
        </View>

        <Text style={styles.sectionTitle}>How you earn</Text>
        <View style={styles.tier}><Text style={styles.tierEmoji}>📱</Text><Text style={styles.tierText}>Friend installs</Text><Text style={styles.tierAmt}>+500 MFB</Text></View>
        <View style={styles.tier}><Text style={styles.tierEmoji}>📝</Text><Text style={styles.tierText}>Friend completes KYC</Text><Text style={styles.tierAmt}>+1000 MFB</Text></View>
        <View style={styles.tier}><Text style={styles.tierEmoji}>💸</Text><Text style={styles.tierText}>Friend first deposit</Text><Text style={styles.tierAmt}>+1500 MFB</Text></View>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: "#0E0F14" },
  center: { flex: 1, backgroundColor: "#0E0F14", justifyContent: "center", alignItems: "center" },
  header: { flexDirection: "row", padding: 16, alignItems: "center", justifyContent: "space-between" },
  title: { color: "#EAEAF0", fontSize: 16, fontWeight: "700" },
  card: { backgroundColor: "#171922", borderRadius: 16, padding: 20, alignItems: "center", borderWidth: 1, borderColor: "#2A2D3A" },
  codeLabel: { color: "#8B8F9E", fontSize: 11, letterSpacing: 1 },
  code: { color: "#FFB100", fontSize: 30, fontWeight: "800", marginTop: 4, letterSpacing: 3 },
  qr: { width: 200, height: 200, backgroundColor: "#fff", marginTop: 16, borderRadius: 8 },
  link: { color: "#8B8F9E", fontSize: 11, marginTop: 12, textAlign: "center" },
  shareBtn: { flexDirection: "row", backgroundColor: "#FFB100", paddingHorizontal: 20, paddingVertical: 12, borderRadius: 12, marginTop: 14, gap: 6 },
  shareTxt: { color: "#0E0F14", fontWeight: "800", fontSize: 14 },
  statsRow: { flexDirection: "row", justifyContent: "space-between", marginTop: 16, gap: 8 },
  statCard: { flex: 1, backgroundColor: "#171922", padding: 12, borderRadius: 10, alignItems: "center", borderWidth: 1, borderColor: "#2A2D3A" },
  statVal: { color: "#EAEAF0", fontSize: 18, fontWeight: "800" },
  statLbl: { color: "#8B8F9E", fontSize: 10, marginTop: 2 },
  sectionTitle: { color: "#EAEAF0", fontSize: 15, fontWeight: "700", marginTop: 22, marginBottom: 10 },
  tier: { flexDirection: "row", alignItems: "center", backgroundColor: "#171922", padding: 14, borderRadius: 10, marginBottom: 8, gap: 12, borderWidth: 1, borderColor: "#2A2D3A" },
  tierEmoji: { fontSize: 22 },
  tierText: { flex: 1, color: "#EAEAF0", fontSize: 13, fontWeight: "600" },
  tierAmt: { color: "#FFB100", fontSize: 13, fontWeight: "800" },
});
