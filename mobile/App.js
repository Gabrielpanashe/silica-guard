import { NavigationContainer } from '@react-navigation/native';
import { createStackNavigator } from '@react-navigation/stack';
import 'react-native-gesture-handler';
import HomeScreen from './src/screens/HomeScreen';
// Import other screens here as you build them:
import IntakeScreen from './src/screens/IntakeScreen';
// import QuestionScreen from './src/screens/QuestionScreen';
// import ResultScreen from './src/screens/ResultScreen';
// import ReferralScreen from './src/screens/ReferralScreen';

const Stack = createStackNavigator();

export default function App() {
  return (
    <NavigationContainer>
      <Stack.Navigator screenOptions={{ headerShown: false }}>
        <Stack.Screen name="Home"     component={HomeScreen} />
        {/* Add screens below as you build them: */}
        { <Stack.Screen name="Intake"   component={IntakeScreen} /> }
        {/* <Stack.Screen name="Question" component={QuestionScreen} /> */}
        {/* <Stack.Screen name="Result"   component={ResultScreen} /> */}
        {/* <Stack.Screen name="Referral" component={ReferralScreen} /> */}
      </Stack.Navigator>
    </NavigationContainer>
  );
}
