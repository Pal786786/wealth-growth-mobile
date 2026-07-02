import React, { useCallback, useEffect, useMemo, useState } from "react";
import { View, Text, StyleSheet, ScrollView, Pressable, TextInput, ActivityIndicator, Alert, Image, KeyboardAvoidingView, Platform } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { LinearGradient } from "expo-linear-gradient";
import * as ImagePicker from "expo-image-picker";
import AsyncStorage from "@react-native-async-storage/async-storage";
import { ChevronLeft, Camera, Upload, CheckCircle2, ChevronRight, X, Edit3, Send } from "lucide-react-native";
import { kycApi, imageAssetToBase64 } from "@/src/api/kyc";

const RESUME_KEY = "mfb.kyc.resume";

type Step = 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8; // 8 = review
type Form = {
  s1: { full_name: string; father_name: string; dob: string; gender: string; occupation: string; annual_income: string; marital_status: string };
  s2: { line1: string; line2: string; city: string; state: string; pincode: string; country: string };
  s3: { pan: string; image_uri?: string; image_b64?: string; mime?: string; pan_masked?: string };
  s4: { aadhaar: string; front_uri?: string; front_b64?: string; back_uri?: string; back_b64?: string; aadhaar_masked?: string };
  s5: { selfie_uri?: string; selfie_b64?: string; mime?: string };
  s6: { holder: string; bank_name: string; ifsc: string; account_number: string; cheque_uri?: string; cheque_b64?: string; account_masked?: string };
  s7: { name: string; relationship: string; dob: string; mobile: string };
};

const blank: Form = {
  s1: { full_name: "", father_name: "", dob: "", gender: "", occupation: "", annual_income: "", marital_status: "" },
  s2: { line1: "", line2: "", city: "", state: "", pincode: "", country: "India" },
  s3: { pan: "" },
  s4: { aadhaar: "" },
  s5: {},
  s6: { holder: "", bank_name: "", ifsc: "", account_number: "" },
  s7: { name: "", relationship: "", dob: "", mobile: "" },
};

const GENDERS = ["Male", "Female", "Other"];
const MARITAL = ["Single", "Married", "Divorced", "Widowed"];
const INCOME = ["< 2 Lakh", "2-5 Lakh", "5-10 Lakh", "10-25 Lakh", "25 Lakh+"];
const RELATIONS = ["Spouse", "Parent", "Sibling", "Child", "Other"];
const STEP_TITLES = ["Personal Details", "Address", "PAN Verification", "Aadhaar Verification", "Selfie Verification", "Bank Account", "Nominee Details", "Review & Submit"];

export default function KycWizard() {
  const router = useRouter();
  const [step, setStep] = useState<Step>(1);
  const [form, setForm] = useState<Form>(blank);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);
  const [initialising, setInitialising] = useState(true);

  // Load resume state on mount
  useEffect(() => {
    (async () => {
      try {
        const [rawForm, rawStep, profile] = await Promise.all([
          AsyncStorage.getItem(RESUME_KEY),
          AsyncStorage.getItem(RESUME_KEY + ".step"),
          kycApi.status().catch(() => null),
        ]);
        if (rawForm) setForm({ ...blank, ...JSON.parse(rawForm) });
        // If backend has steps already, prefer resuming past them
        if (profile) {
          const backendMax = [1,2,3,4,5,6,7].filter(i => profile.steps[String(i)]).length;
          if (backendMax >= 7) setStep(8);
          else if (rawStep) setStep(Math.max(Number(rawStep) as Step, (backendMax + 1) as Step));
          else setStep((backendMax + 1) as Step);
        }
      } catch (e) { /* ignore */ }
      setInitialising(false);
    })();
  }, []);

  // Persist on every change
  useEffect(() => {
    if (!initialising) {
      AsyncStorage.setItem(RESUME_KEY, JSON.stringify(form)).catch(() => {});
      AsyncStorage.setItem(RESUME_KEY + ".step", String(step)).catch(() => {});
    }
  }, [form, step, initialising]);

  const completion = Math.round(((step - 1) / 7) * 100);

  // Validation per step
  const validateStep = (s: Step): boolean => {
    const e: Record<string, string> = {};
    if (s === 1) {
      if (form.s1.full_name.trim().length < 2) e.full_name = "Enter your full name";
      if (!form.s1.dob) e.dob = "DOB required (YYYY-MM-DD)";
      else if (!/^\d{4}-\d{2}-\d{2}$/.test(form.s1.dob)) e.dob = "Format YYYY-MM-DD";
      if (!form.s1.gender) e.gender = "Select gender";
      if (!form.s1.annual_income) e.annual_income = "Select income range";
    }
    if (s === 2) {
      if (!form.s2.line1) e.line1 = "Address line 1 required";
      if (!form.s2.city) e.city = "City required";
      if (!form.s2.state) e.state = "State required";
      if (!/^\d{6}$/.test(form.s2.pincode)) e.pincode = "6-digit PIN";
    }
    if (s === 3) {
      if (!/^[A-Z]{5}[0-9]{4}[A-Z]$/.test(form.s3.pan.toUpperCase())) e.pan = "Format ABCDE1234F";
      if (!form.s3.image_uri) e.image = "Upload PAN photo";
    }
    if (s === 4) {
      if (!/^\d{12}$/.test(form.s4.aadhaar.replace(/\D/g, ""))) e.aadhaar = "12 digits required";
      if (!form.s4.front_uri) e.front = "Upload Aadhaar front";
      if (!form.s4.back_uri) e.back = "Upload Aadhaar back";
    }
    if (s === 5) {
      if (!form.s5.selfie_uri) e.selfie = "Take a selfie";
    }
    if (s === 6) {
      if (!form.s6.holder) e.holder = "Account holder name required";
      if (!form.s6.bank_name) e.bank_name = "Bank name required";
      if (!/^[A-Z]{4}0[A-Z0-9]{6}$/.test(form.s6.ifsc.toUpperCase())) e.ifsc = "Invalid IFSC";
      if (form.s6.account_number.length < 8) e.account_number = "Enter valid account number";
    }
    if (s === 7) {
      if (!form.s7.name) e.n_name = "Nominee name required";
      if (!form.s7.relationship) e.n_rel = "Select relationship";
      if (!/^\d{10}$/.test(form.s7.mobile)) e.n_mobile = "10-digit mobile";
      if (!/^\d{4}-\d{2}-\d{2}$/.test(form.s7.dob)) e.n_dob = "DOB YYYY-MM-DD";
    }
    setErrors(e);
    return Object.keys(e).length === 0;
  };

  const pickImage = async (source: "camera" | "library"): Promise<{ uri: string; b64: string; mime: string } | null> => {
    try {
      const perm = source === "camera"
        ? await ImagePicker.requestCameraPermissionsAsync()
        : await ImagePicker.requestMediaLibraryPermissionsAsync();
      if (!perm.granted) {
        Alert.alert("Permission needed", `Please grant ${source} access to upload documents.`);
        return null;
      }
      const res = await (source === "camera"
        ? ImagePicker.launchCameraAsync({ mediaTypes: ["images"], base64: true, quality: 0.7, allowsEditing: true })
        : ImagePicker.launchImageLibraryAsync({ mediaTypes: ["images"], base64: true, quality: 0.7, allowsEditing: true }));
      if (res.canceled || !res.assets?.[0]) return null;
      const asset = res.assets[0];
      const { b64, mime } = await imageAssetToBase64(asset as any);
      return { uri: asset.uri, b64, mime };
    } catch (e: any) { Alert.alert("Image error", String(e?.message || e)); return null; }
  };

  const askSource = (cb: (src: "camera" | "library") => void) => {
    Alert.alert("Upload", "Choose source", [
      { text: "Camera", onPress: () => cb("camera") },
      { text: "Gallery", onPress: () => cb("library") },
      { text: "Cancel", style: "cancel" },
    ]);
  };

  const submitStep = async () => {
    if (!validateStep(step)) return;
    setSaving(true);
    try {
      if (step === 1) await kycApi.submitStep(1, form.s1);
      else if (step === 2) await kycApi.submitStep(2, form.s2);
      else if (step === 3) {
        const r = await kycApi.submitStep(3, { pan: form.s3.pan.toUpperCase(), image_b64: form.s3.image_b64, mime: form.s3.mime });
        setForm(f => ({ ...f, s3: { ...f.s3, pan_masked: r.steps?.["3"]?.pan_masked } }));
      } else if (step === 4) {
        const r = await kycApi.submitStep(4, { aadhaar: form.s4.aadhaar.replace(/\D/g, ""), front_b64: form.s4.front_b64, back_b64: form.s4.back_b64 });
        setForm(f => ({ ...f, s4: { ...f.s4, aadhaar_masked: r.steps?.["4"]?.aadhaar_masked } }));
      } else if (step === 5) await kycApi.submitStep(5, { image_b64: form.s5.selfie_b64 });
      else if (step === 6) {
        const r = await kycApi.submitStep(6, { holder: form.s6.holder, bank_name: form.s6.bank_name, ifsc: form.s6.ifsc.toUpperCase(), account_number: form.s6.account_number, cheque_b64: form.s6.cheque_b64 });
        setForm(f => ({ ...f, s6: { ...f.s6, account_masked: r.steps?.["6"]?.account_masked } }));
      } else if (step === 7) await kycApi.submitStep(7, form.s7);
      setStep(s => (s + 1) as Step);
      setErrors({});
    } catch (e: any) {
      const msg = e?.response?.data?.detail || e?.message || "Server error";
      Alert.alert("Save failed", typeof msg === "string" ? msg : JSON.stringify(msg));
    } finally { setSaving(false); }
  };

  const finalSubmit = async () => {
    setSaving(true);
    try {
      await kycApi.finalSubmit();
      await AsyncStorage.removeItem(RESUME_KEY);
      await AsyncStorage.removeItem(RESUME_KEY + ".step");
      Alert.alert("KYC Submitted ✅", "Your KYC is now under review. Approval typically within 24 hours.", [
        { text: "OK", onPress: () => router.replace("/kyc") },
      ]);
    } catch (e: any) {
      Alert.alert("Submit failed", e?.response?.data?.detail || e.message);
    } finally { setSaving(false); }
  };

  if (initialising) return <SafeAreaView style={styles.container}><ActivityIndicator size="large" color="#D4AF37" style={{ marginTop: 100 }} /></SafeAreaView>;

  return (
    <SafeAreaView style={styles.container} edges={["top"]}>
      <LinearGradient colors={["#0F172A", "#1E293B"]} style={styles.header}>
        <View style={styles.headerRow}>
          <Pressable onPress={() => step > 1 ? setStep(s => (s - 1) as Step) : router.back()} style={styles.backBtn}>
            <ChevronLeft color="#F8FAFC" size={22} />
          </Pressable>
          <Text style={styles.headerTitle}>Step {Math.min(step, 7)} of 7</Text>
          <Pressable onPress={() => router.replace("/kyc")} style={styles.backBtn}><X color="#94A3B8" size={18} /></Pressable>
        </View>
        <Text style={styles.stepName}>{STEP_TITLES[step - 1]}</Text>
        <View style={styles.progTrack}>
          <LinearGradient colors={["#F0CC5C", "#D4AF37"]} start={{x:0,y:0}} end={{x:1,y:0}}
            style={[styles.progFill, { width: `${step === 8 ? 100 : completion}%` }]} />
        </View>
      </LinearGradient>

      <KeyboardAvoidingView behavior={Platform.OS === "ios" ? "padding" : undefined} style={{ flex: 1 }}>
        <ScrollView style={{ flex: 1 }} contentContainerStyle={styles.body} keyboardShouldPersistTaps="handled">
          {step === 1 && <StepPersonal form={form} setForm={setForm} errors={errors} />}
          {step === 2 && <StepAddress form={form} setForm={setForm} errors={errors} />}
          {step === 3 && <StepPAN form={form} setForm={setForm} errors={errors} askSource={askSource} pickImage={pickImage} />}
          {step === 4 && <StepAadhaar form={form} setForm={setForm} errors={errors} askSource={askSource} pickImage={pickImage} />}
          {step === 5 && <StepSelfie form={form} setForm={setForm} errors={errors} pickImage={pickImage} />}
          {step === 6 && <StepBank form={form} setForm={setForm} errors={errors} askSource={askSource} pickImage={pickImage} />}
          {step === 7 && <StepNominee form={form} setForm={setForm} errors={errors} />}
          {step === 8 && <StepReview form={form} onEdit={(s) => setStep(s)} />}
        </ScrollView>

        <View style={styles.footer}>
          {step < 8 ? (
            <Pressable onPress={submitStep} disabled={saving} style={({ pressed }) => [styles.cta, (saving || pressed) && { opacity: 0.7 }]}>
              <LinearGradient colors={["#F0CC5C", "#D4AF37", "#B8941F"]} start={{x:0,y:0}} end={{x:1,y:0}} style={styles.ctaGrad}>
                {saving ? <ActivityIndicator color="#0F172A" /> : (<><Text style={styles.ctaText}>Save & Continue</Text><ChevronRight color="#0F172A" size={20} strokeWidth={2.5} /></>)}
              </LinearGradient>
            </Pressable>
          ) : (
            <Pressable onPress={finalSubmit} disabled={saving} style={({ pressed }) => [styles.cta, (saving || pressed) && { opacity: 0.7 }]}>
              <LinearGradient colors={["#10B981", "#059669"]} start={{x:0,y:0}} end={{x:1,y:0}} style={styles.ctaGrad}>
                {saving ? <ActivityIndicator color="#FFF" /> : (<><Send color="#FFF" size={18} strokeWidth={2.5} /><Text style={[styles.ctaText, { color: "#FFF" }]}>Submit for Review</Text></>)}
              </LinearGradient>
            </Pressable>
          )}
        </View>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

// --- Sub-components ---
type PP = { form: Form; setForm: (f: any) => void; errors: Record<string,string> };
type PPImg = PP & { askSource: (cb: (s: "camera"|"library") => void) => void; pickImage: (s: "camera"|"library") => Promise<any> };

function Input({ label, value, onChange, err, ...p }: any) {
  return (
    <View style={{ marginBottom: 14 }}>
      <Text style={styles.label}>{label}</Text>
      <TextInput value={value} onChangeText={onChange} style={[styles.input, err && styles.inputErr]} placeholderTextColor="#94A3B8" {...p} />
      {err && <Text style={styles.errMsg}>{err}</Text>}
    </View>
  );
}

function Chips({ label, options, value, onChange, err }: any) {
  return (
    <View style={{ marginBottom: 14 }}>
      <Text style={styles.label}>{label}</Text>
      <View style={styles.chipsRow}>
        {options.map((opt: string) => (
          <Pressable key={opt} onPress={() => onChange(opt)} style={[styles.chip, value === opt && styles.chipActive]}>
            <Text style={[styles.chipText, value === opt && styles.chipTextActive]}>{opt}</Text>
          </Pressable>
        ))}
      </View>
      {err && <Text style={styles.errMsg}>{err}</Text>}
    </View>
  );
}

function UploadBox({ label, uri, onPick, err }: any) {
  return (
    <View style={{ marginBottom: 14 }}>
      <Text style={styles.label}>{label}</Text>
      <Pressable onPress={onPick} style={[styles.uploadBox, err && styles.inputErr]}>
        {uri ? <>
          <Image source={{ uri }} style={styles.uploadPreview} />
          <View style={styles.uploadOverlay}><Text style={styles.uploadReplace}>Tap to replace</Text></View>
        </> : <>
          <Upload color="#94A3B8" size={26} />
          <Text style={styles.uploadHint}>Tap to upload</Text>
          <Text style={styles.uploadSubHint}>Camera or Gallery</Text>
        </>}
      </Pressable>
      {err && <Text style={styles.errMsg}>{err}</Text>}
    </View>
  );
}

function StepPersonal({ form, setForm, errors }: PP) {
  const f = form.s1;
  const u = (k: keyof typeof f, v: string) => setForm((prev: Form) => ({ ...prev, s1: { ...prev.s1, [k]: v } }));
  return (<View>
    <Input label="Full Name*" value={f.full_name} onChange={(v: string) => u("full_name", v)} placeholder="As per PAN" err={errors.full_name} />
    <Input label="Father's Name" value={f.father_name} onChange={(v: string) => u("father_name", v)} placeholder="Optional" />
    <Input label="Date of Birth*" value={f.dob} onChange={(v: string) => u("dob", v)} placeholder="YYYY-MM-DD" err={errors.dob} />
    <Chips label="Gender*" options={GENDERS} value={f.gender} onChange={(v: string) => u("gender", v.toLowerCase())} err={errors.gender} />
    <Input label="Occupation" value={f.occupation} onChange={(v: string) => u("occupation", v)} placeholder="e.g. Engineer" />
    <Chips label="Annual Income*" options={INCOME} value={f.annual_income} onChange={(v: string) => u("annual_income", v)} err={errors.annual_income} />
    <Chips label="Marital Status" options={MARITAL} value={f.marital_status} onChange={(v: string) => u("marital_status", v.toLowerCase())} />
  </View>);
}

function StepAddress({ form, setForm, errors }: PP) {
  const f = form.s2;
  const u = (k: keyof typeof f, v: string) => setForm((prev: Form) => ({ ...prev, s2: { ...prev.s2, [k]: v } }));
  return (<View>
    <Input label="Address Line 1*" value={f.line1} onChange={(v: string) => u("line1", v)} err={errors.line1} />
    <Input label="Address Line 2" value={f.line2} onChange={(v: string) => u("line2", v)} placeholder="Optional" />
    <Input label="City*" value={f.city} onChange={(v: string) => u("city", v)} err={errors.city} />
    <Input label="State*" value={f.state} onChange={(v: string) => u("state", v)} err={errors.state} />
    <Input label="PIN Code*" value={f.pincode} onChange={(v: string) => u("pincode", v.replace(/\D/g,"").slice(0,6))} keyboardType="numeric" err={errors.pincode} />
    <Input label="Country" value={f.country} onChange={(v: string) => u("country", v)} />
  </View>);
}

function StepPAN({ form, setForm, errors, askSource, pickImage }: PPImg) {
  const f = form.s3;
  return (<View>
    <Input label="PAN Number*" value={f.pan} onChange={(v: string) => setForm((p: Form) => ({ ...p, s3: { ...p.s3, pan: v.toUpperCase() } }))}
      placeholder="ABCDE1234F" autoCapitalize="characters" maxLength={10} err={errors.pan} />
    <UploadBox label="PAN Card Image*" uri={f.image_uri} err={errors.image}
      onPick={() => askSource(async (src) => { const img = await pickImage(src); if (img) setForm((p: Form) => ({ ...p, s3: { ...p.s3, image_uri: img.uri, image_b64: img.b64, mime: img.mime } })); })} />
    {f.pan_masked && <View style={styles.okCard}><CheckCircle2 color="#10B981" size={16} /><Text style={styles.okText}>Verified: {f.pan_masked}</Text></View>}
  </View>);
}

function StepAadhaar({ form, setForm, errors, askSource, pickImage }: PPImg) {
  const f = form.s4;
  return (<View>
    <Input label="Aadhaar Number*" value={f.aadhaar} onChange={(v: string) => setForm((p: Form) => ({ ...p, s4: { ...p.s4, aadhaar: v.replace(/\D/g,"").slice(0,12) } }))}
      keyboardType="numeric" placeholder="12-digit Aadhaar" maxLength={12} err={errors.aadhaar} />
    <UploadBox label="Front side*" uri={f.front_uri} err={errors.front}
      onPick={() => askSource(async (src) => { const img = await pickImage(src); if (img) setForm((p: Form) => ({ ...p, s4: { ...p.s4, front_uri: img.uri, front_b64: img.b64 } })); })} />
    <UploadBox label="Back side*" uri={f.back_uri} err={errors.back}
      onPick={() => askSource(async (src) => { const img = await pickImage(src); if (img) setForm((p: Form) => ({ ...p, s4: { ...p.s4, back_uri: img.uri, back_b64: img.b64 } })); })} />
    {f.aadhaar_masked && <View style={styles.okCard}><CheckCircle2 color="#10B981" size={16} /><Text style={styles.okText}>Verified: {f.aadhaar_masked}</Text></View>}
  </View>);
}

function StepSelfie({ form, setForm, errors, pickImage }: PPImg) {
  const f = form.s5;
  return (<View style={{ alignItems: "center" }}>
    <Text style={{ color: "#64748B", textAlign: "center", marginBottom: 20 }}>
      Position your face inside the frame with good lighting.{"\n"}Remove glasses & headwear for best results.
    </Text>
    <Pressable onPress={async () => { const img = await pickImage("camera"); if (img) setForm((p: Form) => ({ ...p, s5: { selfie_uri: img.uri, selfie_b64: img.b64, mime: img.mime } })); }}
      style={styles.selfieCircle}>
      {f.selfie_uri ? <Image source={{ uri: f.selfie_uri }} style={styles.selfieImg} /> : (<><Camera color="#D4AF37" size={44} /><Text style={styles.selfieHint}>Tap to capture</Text></>)}
    </Pressable>
    {f.selfie_uri && <Pressable onPress={async () => { const img = await pickImage("camera"); if (img) setForm((p: Form) => ({ ...p, s5: { selfie_uri: img.uri, selfie_b64: img.b64, mime: img.mime } })); }} style={styles.retakeBtn}><Text style={styles.retakeText}>Retake</Text></Pressable>}
    {errors.selfie && <Text style={[styles.errMsg, { marginTop: 12 }]}>{errors.selfie}</Text>}
  </View>);
}

function StepBank({ form, setForm, errors, askSource, pickImage }: PPImg) {
  const f = form.s6;
  const u = (k: keyof typeof f, v: string) => setForm((prev: Form) => ({ ...prev, s6: { ...prev.s6, [k]: v } }));
  return (<View>
    <Input label="Account Holder Name*" value={f.holder} onChange={(v: string) => u("holder", v)} err={errors.holder} />
    <Input label="Bank Name*" value={f.bank_name} onChange={(v: string) => u("bank_name", v)} placeholder="e.g. HDFC Bank" err={errors.bank_name} />
    <Input label="IFSC Code*" value={f.ifsc} onChange={(v: string) => u("ifsc", v.toUpperCase())} placeholder="HDFC0001234" autoCapitalize="characters" maxLength={11} err={errors.ifsc} />
    <Input label="Account Number*" value={f.account_number} onChange={(v: string) => u("account_number", v.replace(/\D/g,""))} keyboardType="numeric" err={errors.account_number} />
    <UploadBox label="Cancelled Cheque (optional but recommended)" uri={f.cheque_uri}
      onPick={() => askSource(async (src) => { const img = await pickImage(src); if (img) setForm((p: Form) => ({ ...p, s6: { ...p.s6, cheque_uri: img.uri, cheque_b64: img.b64 } })); })} />
    {f.account_masked && <View style={styles.okCard}><CheckCircle2 color="#10B981" size={16} /><Text style={styles.okText}>Saved: {f.account_masked}</Text></View>}
  </View>);
}

function StepNominee({ form, setForm, errors }: PP) {
  const f = form.s7;
  const u = (k: keyof typeof f, v: string) => setForm((prev: Form) => ({ ...prev, s7: { ...prev.s7, [k]: v } }));
  return (<View>
    <Input label="Nominee Name*" value={f.name} onChange={(v: string) => u("name", v)} err={errors.n_name} />
    <Chips label="Relationship*" options={RELATIONS} value={f.relationship} onChange={(v: string) => u("relationship", v.toLowerCase())} err={errors.n_rel} />
    <Input label="Nominee DOB*" value={f.dob} onChange={(v: string) => u("dob", v)} placeholder="YYYY-MM-DD" err={errors.n_dob} />
    <Input label="Nominee Mobile*" value={f.mobile} onChange={(v: string) => u("mobile", v.replace(/\D/g,"").slice(0,10))} keyboardType="numeric" err={errors.n_mobile} />
  </View>);
}

function StepReview({ form, onEdit }: { form: Form; onEdit: (s: Step) => void }) {
  const rows: [number, string, string][] = [
    [1, "Full Name", form.s1.full_name],
    [1, "DOB", form.s1.dob],
    [1, "Gender", form.s1.gender],
    [1, "Income", form.s1.annual_income],
    [2, "Address", `${form.s2.line1}, ${form.s2.city} ${form.s2.pincode}`],
    [3, "PAN", form.s3.pan_masked || form.s3.pan],
    [4, "Aadhaar", form.s4.aadhaar_masked || "XXXX-XXXX-" + form.s4.aadhaar.slice(-4)],
    [5, "Selfie", form.s5.selfie_uri ? "Uploaded" : "—"],
    [6, "Bank", `${form.s6.bank_name} · ${form.s6.account_masked || form.s6.account_number.slice(-4)}`],
    [7, "Nominee", `${form.s7.name} (${form.s7.relationship})`],
  ];
  return (<View>
    <Text style={{ color: "#64748B", marginBottom: 16, textAlign: "center", lineHeight: 20 }}>
      Review your information carefully. Once submitted for review, KYC will be locked until admin approves.
    </Text>
    {rows.map(([s, k, v], i) => (
      <Pressable key={i} onPress={() => onEdit(s as Step)} style={styles.reviewRow}>
        <View style={{ flex: 1 }}>
          <Text style={styles.reviewLabel}>{k}</Text>
          <Text style={styles.reviewValue}>{v || "—"}</Text>
        </View>
        <Edit3 color="#94A3B8" size={16} />
      </Pressable>
    ))}
  </View>);
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#F8FAFC" },
  header: { padding: 16, paddingBottom: 20 },
  headerRow: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", marginBottom: 10 },
  backBtn: { padding: 8, borderRadius: 999, backgroundColor: "rgba(255,255,255,0.05)" },
  headerTitle: { color: "#94A3B8", fontSize: 12, fontWeight: "700", letterSpacing: 1.5, textTransform: "uppercase" },
  stepName: { color: "#F8FAFC", fontSize: 22, fontWeight: "800", marginBottom: 14 },
  progTrack: { height: 4, backgroundColor: "rgba(255,255,255,0.1)", borderRadius: 2, overflow: "hidden" },
  progFill: { height: 4, borderRadius: 2 },
  body: { padding: 20, paddingBottom: 40 },
  footer: { padding: 16, backgroundColor: "#FFF", borderTopWidth: 1, borderTopColor: "#E2E8F0" },

  label: { color: "#0F172A", fontSize: 13, fontWeight: "700", marginBottom: 6 },
  input: { backgroundColor: "#FFF", borderWidth: 1, borderColor: "#E2E8F0", borderRadius: 12, paddingHorizontal: 14, paddingVertical: 12, fontSize: 15, color: "#0F172A" },
  inputErr: { borderColor: "#EF4444" },
  errMsg: { color: "#EF4444", fontSize: 12, marginTop: 4 },
  chipsRow: { flexDirection: "row", flexWrap: "wrap", gap: 8 },
  chip: { paddingHorizontal: 14, paddingVertical: 8, borderRadius: 999, backgroundColor: "#F1F5F9", borderWidth: 1, borderColor: "#E2E8F0" },
  chipActive: { backgroundColor: "#0F172A", borderColor: "#D4AF37" },
  chipText: { color: "#475569", fontSize: 13, fontWeight: "600" },
  chipTextActive: { color: "#F0CC5C" },

  uploadBox: { height: 140, borderRadius: 14, borderWidth: 2, borderColor: "#E2E8F0", borderStyle: "dashed", alignItems: "center", justifyContent: "center", backgroundColor: "#FFF", overflow: "hidden" },
  uploadPreview: { width: "100%", height: "100%", resizeMode: "cover" },
  uploadOverlay: { position: "absolute", bottom: 0, left: 0, right: 0, backgroundColor: "rgba(15,23,42,0.75)", padding: 8 },
  uploadReplace: { color: "#F0CC5C", textAlign: "center", fontSize: 12, fontWeight: "700" },
  uploadHint: { color: "#475569", fontSize: 14, marginTop: 8, fontWeight: "600" },
  uploadSubHint: { color: "#94A3B8", fontSize: 11, marginTop: 2 },

  okCard: { flexDirection: "row", alignItems: "center", gap: 8, backgroundColor: "#D1FAE5", padding: 10, borderRadius: 10, marginTop: 4 },
  okText: { color: "#065F46", fontSize: 13, fontWeight: "700" },

  selfieCircle: { width: 240, height: 240, borderRadius: 120, borderWidth: 3, borderColor: "#D4AF37", borderStyle: "dashed", alignItems: "center", justifyContent: "center", backgroundColor: "#FFF", overflow: "hidden", marginVertical: 20 },
  selfieImg: { width: "100%", height: "100%" },
  selfieHint: { color: "#94A3B8", marginTop: 10, fontSize: 13, fontWeight: "600" },
  retakeBtn: { paddingHorizontal: 24, paddingVertical: 10, borderRadius: 999, backgroundColor: "#F1F5F9", borderWidth: 1, borderColor: "#E2E8F0" },
  retakeText: { color: "#0F172A", fontWeight: "700", fontSize: 13 },

  reviewRow: { flexDirection: "row", alignItems: "center", padding: 14, backgroundColor: "#FFF", borderRadius: 12, marginBottom: 8, borderWidth: 1, borderColor: "#E2E8F0" },
  reviewLabel: { color: "#94A3B8", fontSize: 11, fontWeight: "700", textTransform: "uppercase", letterSpacing: 0.5 },
  reviewValue: { color: "#0F172A", fontSize: 15, fontWeight: "700", marginTop: 2 },

  cta: { borderRadius: 14, overflow: "hidden" },
  ctaGrad: { flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 8, paddingVertical: 15 },
  ctaText: { color: "#0F172A", fontSize: 16, fontWeight: "800" },
});
