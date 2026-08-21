import 'react-native-gesture-handler';
import { NavigationContainer } from '@react-navigation/native';
import { createStackNavigator } from '@react-navigation/stack';
import { SafeAreaProvider } from 'react-native-safe-area-context';
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

const Stack = createStackNavigator();

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
  return (
    <SafeAreaProvider>
      <OutreachSiteProvider>
        <NavigationContainer>
          <Stack.Navigator screenOptions={{ headerShown: false }} initialRouteName="Landing">
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
