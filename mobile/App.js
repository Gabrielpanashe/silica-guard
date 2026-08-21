import 'react-native-gesture-handler';
import { View } from 'react-native';
import { NavigationContainer } from '@react-navigation/native';
import { createStackNavigator } from '@react-navigation/stack';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { useEffect, useState } from 'react';
import AsyncStorage from '@react-native-async-storage/async-storage';
import LandingScreen from './src/screens/LandingScreen';
import HomeScreen from './src/screens/HomeScreen';
// Import other screens here as you build them:
import IntakeScreen from './src/screens/IntakeScreen';
import QuestionScreen from './src/screens/QuestionScreen';
import ResultScreen from './src/screens/ResultScreen';
import ReferralScreen from './src/screens/ReferralScreen';
import WorklistScreen from './src/screens/WorklistScreen';
import OutreachStatsScreen from './src/screens/OutreachStatsScreen';
import { OutreachSiteProvider } from './src/context/OutreachSiteContext';
import { light } from './src/theme';

const Stack = createStackNavigator();

// Set by LandingScreen.js once "Get Started" is tapped — read here so
// Landing only ever shows on a device's genuine first run, not every app
// open. A VHW opens this app many times a day in the field; a splash
// screen every single time would get old fast. See LandingScreen.js for
// where the flag actually gets written.
const SEEN_LANDING_KEY = 'sg_has_seen_landing';

// SafeAreaProvider (12 August) — was missing entirely. Every screen's
// SafeAreaView now imports from react-native-safe-area-context instead of
// core react-native (whose SafeAreaView is iOS-only — a documented no-op
// on Android, rendering as a plain View with zero inset padding). That's
// why header content — the brand, the LIVE pill, the date — sat right up
// against the status bar / notch on a real Android phone even though it
// looked fine on web (no OS status bar there to collide with). This
// provider is required for the context package's SafeAreaView/
// useSafeAreaInsets to resolve real insets at all.
export default function App() {
  // null while the AsyncStorage read is in flight — NavigationContainer
  // needs a resolved initialRouteName at mount (it can't be changed
  // afterwards without an explicit reset), so the navigator itself isn't
  // rendered until this settles. Defaults to "Landing" (i.e. show it) on
  // any read failure — the safer default for a first-run gate is to show
  // the screen, not silently skip it.
  const [initialRoute, setInitialRoute] = useState(null);

  useEffect(() => {
    AsyncStorage.getItem(SEEN_LANDING_KEY)
      .then((seen) => setInitialRoute(seen === 'true' ? 'Home' : 'Landing'))
      .catch(() => setInitialRoute('Landing'));
  }, []);

  if (!initialRoute) {
    // Themed to match Landing's own background so there's no flash of an
    // unstyled screen during the (typically near-instant) storage read.
    return <View style={{ flex: 1, backgroundColor: light.bg }} />;
  }

  return (
    <SafeAreaProvider>
      <OutreachSiteProvider>
        <NavigationContainer>
          <Stack.Navigator screenOptions={{ headerShown: false }} initialRouteName={initialRoute}>
            <Stack.Screen name="Landing"  component={LandingScreen} />
            <Stack.Screen name="Home"     component={HomeScreen} />
            <Stack.Screen name="Intake"   component={IntakeScreen} />
            <Stack.Screen name="Question" component={QuestionScreen} />
            <Stack.Screen name="Result"   component={ResultScreen} />
            <Stack.Screen name="Referral" component={ReferralScreen} />
            <Stack.Screen name="Worklist" component={WorklistScreen} />
            <Stack.Screen name="OutreachStats" component={OutreachStatsScreen} />
          </Stack.Navigator>
        </NavigationContainer>
      </OutreachSiteProvider>
    </SafeAreaProvider>
  );
}
