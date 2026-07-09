import React, { useCallback, useState } from "react";
import { View, Text, StyleSheet, ScrollView, Pressable, Image, ActivityIndicator } from "react-native";
import { useRouter, useFocusEffect } from "expo-router";
import { Plane, Building2, Bus, TrainFront, Star, MapPin, ArrowRight } from "lucide-react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useTheme } from "@/src/theme/ThemeProvider";
import { api } from "@/src/api/client";
import { Card } from "@/src/components/Card";
import { useToast } from "@/src/components/Toast";
import { formatINR } from "@/src/utils/format";

const HOTEL_IMG = "https://images.unsplash.com/photo-1566073771259-6a8506099945?auto=format&fit=crop&q=80&w=1000";
const FLIGHT_IMG = "https://images.unsplash.com/photo-1436491865332-7a61a109cc05?auto=format&fit=crop&q=80&w=1000";

export default function TravelTab() {
  const { palette } = useTheme();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const { show } = useToast();
  const [tab, setTab] = useState<"flight" | "hotel" | "bus" | "train">("flight");
  const [flights, setFlights] = useState<any[]>([]);
  const [hotels, setHotels] = useState<any[]>([]);
  const [buses, setBuses] = useState<any[]>([]);
  const [trains, setTrains] = useState<any[]>([]);
  const [bookings, setBookings] = useState<any[]>([]);
  const [showHistory, setShowHistory] = useState(true);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [{ data: f }, { data: h }, { data: b }, { data: t }, { data: bk }] = await Promise.all([
        api.get("/travel/flights"),
        api.get("/travel/hotels"),
        api.get("/travel/buses").catch(() => ({ data: [] })),
        api.get("/travel/trains").catch(() => ({ data: [] })),
        api.get("/travel/bookings").catch(() => ({ data: [] })),
      ]);
      setFlights(f); setHotels(h); setBuses(b); setTrains(t); setBookings(bk);
    } catch {} finally { setLoading(false); }
  }, []);

  useFocusEffect(useCallback(() => { load(); }, [load]));

  const book = async (type: string, title: string, amount: number, meta: any, from?: string, to?: string) => {
    try {
      const date = new Date(); date.setDate(date.getDate() + 7);
      const { data } = await api.post("/travel/book", {
        booking_type: type, title, amount, meta,
        from_loc: from, to_loc: to,
        travel_date: date.toISOString().slice(0, 10),
        passengers: 1,
      });
      const cb = data?.cashback?.cashback_amount || 0;
      const pts = data?.cashback?.points_added || 0;
      show("success", `${(type || "trip").charAt(0).toUpperCase() + (type || "trip").slice(1)} booked!${cb ? ` +₹${cb} cashback` : ""}${pts ? ` · +${pts} pts` : ""}`);
      load();
    } catch (e: any) {
      show("error", e?.response?.data?.detail || "Booking failed");
    }
  };

  const cancel = async (bookingId: string) => {
    try {
      const { data } = await api.post(`/travel/cancel/${bookingId}`, { reason: "User cancelled" });
      show("success", data.message);
      load();
    } catch (e: any) {
      show("error", e?.response?.data?.detail || "Cancellation failed");
    }
  };

  const tabs = [
    { id: "flight", label: "Flights", icon: Plane },
    { id: "hotel", label: "Hotels", icon: Building2 },
    { id: "bus", label: "Bus", icon: Bus },
    { id: "train", label: "Train", icon: TrainFront },
  ] as const;

  return (
    <View style={[s.root, { backgroundColor: palette.background }]}>
      <View style={[s.hdr, { paddingTop: insets.top + 8 }]}>
        <Text style={[s.title, { color: palette.textPrimary }]}>Travel</Text>
        <Text style={[s.subtitle, { color: palette.textSecondary }]}>Book flights, hotels & more</Text>
      </View>

      <ScrollView contentContainerStyle={[s.scroll, { paddingBottom: 110 }]}>
        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={s.tabsRow}>
          {tabs.map((t) => (
            <Pressable
              key={t.id}
              onPress={() => setTab(t.id)}
              style={[
                s.chip,
                {
                  backgroundColor: tab === t.id ? palette.primary : palette.surface,
                  borderColor: tab === t.id ? palette.primary : palette.border,
                },
              ]}
              testID={`travel-tab-${t.id}`}
            >
              <t.icon color={tab === t.id ? "#fff" : palette.textPrimary} size={16} />
              <Text style={{ color: tab === t.id ? "#fff" : palette.textPrimary, fontSize: 13, fontWeight: "700" }}>
                {t.label}
              </Text>
            </Pressable>
          ))}
        </ScrollView>

        {loading ? <ActivityIndicator color={palette.primary} style={{ marginTop: 30 }} /> : null}

        {!loading && tab === "flight" && (
          <View style={{ gap: 12 }}>
            <Image source={{ uri: FLIGHT_IMG }} style={s.hero} />
            <Text style={[s.section, { color: palette.textPrimary }]}>Best deals today</Text>
            {flights.map((f) => (
              <Card key={f.code} style={{ gap: 10 }}>
                <View style={s.flightRow}>
                  <Text style={[s.airline, { color: palette.textPrimary }]}>{f.airline} • {f.code}</Text>
                  <Text style={[s.price, { color: palette.primary }]}>{formatINR(f.price)}</Text>
                </View>
                <View style={s.flightRoute}>
                  <View style={{ alignItems: "flex-start" }}>
                    <Text style={[s.routeTime, { color: palette.textPrimary }]}>{f.depart}</Text>
                    <Text style={[s.routeCode, { color: palette.textSecondary }]}>{f.from}</Text>
                  </View>
                  <View style={s.dashedLine}>
                    <Text style={[s.duration, { color: palette.textMuted }]}>{f.duration}</Text>
                    <ArrowRight color={palette.textMuted} size={16} />
                  </View>
                  <View style={{ alignItems: "flex-end" }}>
                    <Text style={[s.routeTime, { color: palette.textPrimary }]}>{f.arrive}</Text>
                    <Text style={[s.routeCode, { color: palette.textSecondary }]}>{f.to}</Text>
                  </View>
                </View>
                <Pressable
                  onPress={() => book("flight", `${f.airline} ${f.code} ${f.from}→${f.to}`, f.price, f, f.from, f.to)}
                  style={[s.bookBtn, { backgroundColor: palette.primary }]}
                  testID={`book-flight-${f.code}`}
                >
                  <Text style={s.bookTxt}>Book Flight</Text>
                </Pressable>
              </Card>
            ))}
          </View>
        )}

        {!loading && tab === "hotel" && (
          <View style={{ gap: 12 }}>
            <Image source={{ uri: HOTEL_IMG }} style={s.hero} />
            <Text style={[s.section, { color: palette.textPrimary }]}>Featured stays</Text>
            {hotels.map((h, i) => (
              <Card key={i} style={{ gap: 8 }}>
                <Text style={[s.hotelName, { color: palette.textPrimary }]}>{h.name}</Text>
                <View style={{ flexDirection: "row", alignItems: "center", gap: 6 }}>
                  <MapPin color={palette.textSecondary} size={14} />
                  <Text style={[s.hotelMeta, { color: palette.textSecondary }]}>{h.city}</Text>
                  <Star color={palette.warning} size={14} fill={palette.warning} />
                  <Text style={[s.hotelMeta, { color: palette.textSecondary }]}>{h.rating}</Text>
                </View>
                <View style={s.flightRow}>
                  <Text style={[s.hotelPrice, { color: palette.textPrimary }]}>{formatINR(h.price_per_night)} <Text style={{ color: palette.textMuted, fontWeight: "500" }}>/ night</Text></Text>
                  <Pressable
                    onPress={() => book("hotel", `${h.name}, ${h.city}`, h.price_per_night, h)}
                    style={[s.bookBtn, { backgroundColor: palette.primary, paddingHorizontal: 18 }]}
                    testID={`book-hotel-${i}`}
                  >
                    <Text style={s.bookTxt}>Book</Text>
                  </Pressable>
                </View>
              </Card>
            ))}
          </View>
        )}

        {!loading && (tab === "bus" || tab === "train") && (
          <View style={{ gap: 12 }}>
            <Text style={[s.section, { color: palette.textPrimary }]}>
              {tab === "bus" ? "Bus routes" : "Train routes"} • {(tab === "bus" ? buses : trains).length} options
            </Text>
            {(tab === "bus" ? buses : trains).map((it: any) => (
              <Card key={it.id} style={{ gap: 10 }}>
                <View style={s.flightRow}>
                  <View style={{ flex: 1 }}>
                    <Text style={[s.airline, { color: palette.textPrimary }]} numberOfLines={1}>
                      {tab === "bus" ? `${it.operator} • ${it.type}` : `${it.number} • ${it.name}`}
                    </Text>
                    <Text style={{ fontSize: 11, color: palette.textSecondary, marginTop: 2 }}>
                      {tab === "bus" ? `★ ${it.rating} · ${it.seats_left} seats left` : `★ ${it.rating} · ${(it.classes || []).join(" · ")}`}
                    </Text>
                  </View>
                  <Text style={[s.price, { color: palette.primary }]}>
                    {formatINR(tab === "bus" ? it.price : (it.prices?.["3A"] || it.prices?.["CC"] || it.prices?.["SL"] || 999))}
                  </Text>
                </View>
                <View style={s.flightRoute}>
                  <View style={{ alignItems: "flex-start" }}>
                    <Text style={[s.routeTime, { color: palette.textPrimary }]}>{it.depart}</Text>
                    <Text style={[s.routeCode, { color: palette.textSecondary }]} numberOfLines={1}>{it.from}</Text>
                  </View>
                  <View style={s.dashedLine}>
                    <Text style={[s.duration, { color: palette.textMuted }]}>{it.duration}</Text>
                    <ArrowRight color={palette.textMuted} size={16} />
                  </View>
                  <View style={{ alignItems: "flex-end" }}>
                    <Text style={[s.routeTime, { color: palette.textPrimary }]}>{it.arrive}</Text>
                    <Text style={[s.routeCode, { color: palette.textSecondary }]} numberOfLines={1}>{it.to}</Text>
                  </View>
                </View>
                <Pressable
                  onPress={() => {
                    const price = tab === "bus" ? it.price : (it.prices?.["3A"] || it.prices?.["CC"] || it.prices?.["SL"] || 999);
                    const title = tab === "bus"
                      ? `${it.operator} ${it.from}→${it.to}`
                      : `${it.number} ${it.name} ${it.from}→${it.to}`;
                    book(tab, title, price, it, it.from, it.to);
                  }}
                  style={[s.bookBtn, { backgroundColor: palette.primary }]}
                  testID={`book-${tab}-${it.id}`}
                >
                  <Text style={s.bookTxt}>Book {tab === "bus" ? "Bus" : "Train"}</Text>
                </Pressable>
              </Card>
            ))}
          </View>
        )}

        {/* Booking history section */}
        {bookings.length > 0 ? (
          <View style={{ gap: 10, marginTop: 8 }}>
            <View style={{ flexDirection: "row", alignItems: "center", justifyContent: "space-between" }}>
              <Text style={[s.section, { color: palette.textPrimary }]}>My bookings ({bookings.length})</Text>
              <Pressable onPress={() => setShowHistory((v) => !v)}>
                <Text style={{ color: palette.primary, fontWeight: "700", fontSize: 13 }}>
                  {showHistory ? "Hide" : "Show"}
                </Text>
              </Pressable>
            </View>
            {showHistory ? bookings.map((bk: any) => (
              <Card key={bk.booking_id} style={{ gap: 6 }}>
                <View style={s.flightRow}>
                  <View style={{ flex: 1 }}>
                    <Text style={[s.hotelName, { color: palette.textPrimary }]} numberOfLines={1}>{bk.title}</Text>
                    <Text style={{ fontSize: 11, color: palette.textSecondary, marginTop: 2 }}>
                      {String(bk?.booking_type ?? "trip").toUpperCase()} · {bk?.travel_date ?? "—"} ·{" "}
                      <Text style={{ color: bk.status === "cancelled" ? palette.danger : palette.success, fontWeight: "700" }}>
                        {bk.status === "cancelled" ? `Cancelled (refund ₹${bk.refund_amount || 0})` : "Confirmed"}
                      </Text>
                    </Text>
                  </View>
                  <Text style={[s.price, { color: palette.textPrimary }]}>{formatINR(bk.amount)}</Text>
                </View>
                {bk.status !== "cancelled" ? (
                  <Pressable
                    onPress={() => cancel(bk.booking_id)}
                    style={{ paddingVertical: 8, borderRadius: 10, borderWidth: 1, borderColor: palette.danger, alignItems: "center" }}
                    testID={`cancel-booking-${bk.booking_id}`}
                  >
                    <Text style={{ color: palette.danger, fontWeight: "700", fontSize: 13 }}>Cancel booking</Text>
                  </Pressable>
                ) : null}
              </Card>
            )) : null}
          </View>
        ) : null}
      </ScrollView>
    </View>
  );
}

const s = StyleSheet.create({
  root: { flex: 1 },
  hdr: { paddingHorizontal: 16, paddingBottom: 8 },
  title: { fontSize: 24, fontWeight: "800", letterSpacing: -0.5 },
  subtitle: { fontSize: 13, marginTop: 4 },
  scroll: { paddingHorizontal: 16, paddingTop: 16, gap: 12 },
  tabsRow: { gap: 8, paddingRight: 16, paddingBottom: 4 },
  chip: { flexDirection: "row", alignItems: "center", gap: 6, paddingHorizontal: 14, height: 36, borderRadius: 18, borderWidth: 1, flexShrink: 0 },
  hero: { width: "100%", height: 160, borderRadius: 20 },
  section: { fontSize: 16, fontWeight: "800", marginTop: 4, letterSpacing: -0.3 },
  flightRow: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  airline: { fontSize: 14, fontWeight: "700" },
  price: { fontSize: 18, fontWeight: "800" },
  flightRoute: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  routeTime: { fontSize: 18, fontWeight: "800" },
  routeCode: { fontSize: 12, fontWeight: "600", marginTop: 2 },
  dashedLine: { flex: 1, alignItems: "center", gap: 4 },
  duration: { fontSize: 11, fontWeight: "600" },
  bookBtn: { borderRadius: 12, paddingVertical: 12, alignItems: "center" },
  bookTxt: { color: "#fff", fontSize: 14, fontWeight: "800" },
  hotelName: { fontSize: 16, fontWeight: "800" },
  hotelMeta: { fontSize: 12, fontWeight: "600" },
  hotelPrice: { fontSize: 16, fontWeight: "800" },
});
