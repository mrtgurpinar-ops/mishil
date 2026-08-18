import { Stack } from 'expo-router';

export default function OnboardingLayout() {
  return (
    <Stack screenOptions={{ headerShown: false }}>
      <Stack.Screen name="baby-profile" />
      <Stack.Screen name="wake-window-setup" />
    </Stack>
  );
}
