import { StatusBar } from "expo-status-bar";
import * as Haptics from "expo-haptics";
import * as Notifications from "expo-notifications";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  ActivityIndicator,
  BackHandler,
  Platform,
  StyleSheet,
  View,
} from "react-native";
import { SafeAreaProvider, SafeAreaView } from "react-native-safe-area-context";
import { WebView } from "react-native-webview";
import { BACKEND_URL } from "./src/config";
import { registerForPush } from "./src/push";

// Foreground notifications still show the banner + play sound (SDK 57 API).
Notifications.setNotificationHandler({
  handleNotification: async () => ({
    shouldShowBanner: true,
    shouldShowList: true,
    shouldPlaySound: true,
    shouldSetBadge: false,
  }),
});

// Hybrid v1: the full web app runs in a WebView (already immersive + mobile
// ready); the native layer adds push registration, a hard haptic buzz when a
// slap arrives, and deep-linking a tapped notification to the right stock.
export default function App() {
  const webRef = useRef<WebView>(null);
  const [ready, setReady] = useState(false);
  const [uri, setUri] = useState(BACKEND_URL);
  const canGoBack = useRef(false);

  useEffect(() => {
    registerForPush();

    // A slap landed while the app is open — buzz hard.
    const recv = Notifications.addNotificationReceivedListener((n) => {
      const side = (n.request.content.data as any)?.side;
      Haptics.notificationAsync(
        side === "sell"
          ? Haptics.NotificationFeedbackType.Warning
          : Haptics.NotificationFeedbackType.Success
      );
    });

    // Tapped a notification — open the full slap for that signal (with the
    // advisor's recommendation), not a context-free ticker page.
    const tap = Notifications.addNotificationResponseReceivedListener((r) => {
      const d = (r.notification.request.content.data as any) || {};
      if (d.id) setUri(`${BACKEND_URL}/?slap=${encodeURIComponent(d.id)}&ts=${Date.now()}`);
      else if (d.symbol) setUri(`${BACKEND_URL}/stock/${d.symbol}?ts=${Date.now()}`);
    });

    return () => {
      recv.remove();
      tap.remove();
    };
  }, []);

  // Android hardware back navigates the WebView instead of closing the app.
  useEffect(() => {
    if (Platform.OS !== "android") return;
    const sub = BackHandler.addEventListener("hardwareBackPress", () => {
      if (canGoBack.current) {
        webRef.current?.goBack();
        return true;
      }
      return false;
    });
    return () => sub.remove();
  }, []);

  const onNav = useCallback((s: { canGoBack: boolean }) => {
    canGoBack.current = s.canGoBack;
  }, []);

  return (
    <SafeAreaProvider>
      <SafeAreaView style={styles.root} edges={["top", "left", "right"]}>
        <StatusBar style="light" />
        <WebView
          ref={webRef}
          source={{ uri }}
          style={styles.web}
          onLoadEnd={() => setReady(true)}
          onNavigationStateChange={onNav}
          allowsBackForwardNavigationGestures
          decelerationRate="normal"
          pullToRefreshEnabled
          setSupportMultipleWindows={false}
        />
        {!ready && (
          <View style={styles.loading} pointerEvents="none">
            <ActivityIndicator size="large" color="#38bdf8" />
          </View>
        )}
      </SafeAreaView>
    </SafeAreaProvider>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: "#05070f" },
  web: { flex: 1, backgroundColor: "#05070f" },
  loading: {
    position: "absolute",
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: "#05070f",
  },
});
