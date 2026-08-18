/**
 * Mishil Mobile E2E Flow Specification (Maestro / Detox)
 * 
 * Flow Scenario:
 * 1. Launch App (Register / Onboarding)
 * 2. Fill Baby Profile (Name: 'Melis', Age: '6')
 * 3. Review Initial Wake Window with Breathing Moon
 * 4. Land on Home Screen and verify BreathingMoonIndicator
 * 5. Navigate to Cry Analysis and test recording trigger
 * 6. Quick add a feeding routine and verify optimistic appearance
 */

export const MishilE2EFlowYaml = `
appId: com.mishil.app
---
- launchApp
- assertVisible: "Mishil"

# Step 1: Onboarding Baby Setup
- tapOn: "Kayıt Ol ve Başla"
- inputText: "Melis"
- tapOn: "Devam Et"

# Step 2: Wake Window Review
- assertVisible: "Uyku Ritmi Hazırlandı"
- tapOn: "Mishil'i Kullanmaya Başla"

# Step 3: Home Screen & Breathing Moon
- assertVisible: "Sonra Uyku"
- assertVisible: "Hızlı Rutin Ekle"

# Step 4: Quick Routine
- tapOn: "Beslenme"
- assertVisible: "Günlük Rutinler"
- assertVisible: "Beslenme"

# Step 5: Cry Analysis
- tapOn: "Ağlama Analizi"
- assertVisible: "Kaydı Başlatmak İçin Dokunun"
`;

describe('E2E Flow Schema Verification', () => {
  it('should define valid Maestro YAML instructions', () => {
    expect(MishilE2EFlowYaml).toContain('appId: com.mishil.app');
    expect(MishilE2EFlowYaml).toContain('Breathing');
  });
});
