import { Redirect } from 'expo-router';

export default function Index() {
  // Direct default entry to Home Tab
  return <Redirect href="/(tabs)/home" />;
}
