import { createClient, SupabaseClient, User, Session } from "@supabase/supabase-js";
import { SUPABASE_URL, SUPABASE_ANON_KEY, isAuthEnabled } from "./config";

export let supabase: SupabaseClient | null = null;

if (isAuthEnabled) {
  try {
    supabase = createClient(SUPABASE_URL, SUPABASE_ANON_KEY, {
      auth: {
        persistSession: true,
        autoRefreshToken: true,
        detectSessionInUrl: true,
      },
    });
  } catch (err) {
    console.error("Failed to initialize Supabase client:", err);
  }
}

/**
 * Retrieve the current JWT Bearer access token for API requests.
 */
export async function getAuthToken(): Promise<string | null> {
  if (!supabase) return null;
  try {
    const { data } = await supabase.auth.getSession();
    return data.session?.access_token || null;
  } catch (e) {
    return null;
  }
}

/**
 * Retrieve the current session.
 */
export async function getCurrentSession(): Promise<Session | null> {
  if (!supabase) return null;
  const { data } = await supabase.auth.getSession();
  return data.session;
}

/**
 * Retrieve the currently authenticated user.
 */
export async function getCurrentUser(): Promise<User | null> {
  if (!supabase) return null;
  const { data } = await supabase.auth.getUser();
  return data.user;
}

/**
 * Sign in with email and password.
 */
export async function signInWithEmail(email: string, password: string) {
  if (!supabase) {
    throw new Error("Supabase is not configured. Please set VITE_SUPABASE_URL and VITE_SUPABASE_ANON_KEY.");
  }
  return supabase.auth.signInWithPassword({ email, password });
}

/**
 * Sign out current user.
 */
export async function signOutUser() {
  if (!supabase) return;
  return supabase.auth.signOut();
}

/**
 * Subscribe to authentication state changes.
 */
export function subscribeAuthState(callback: (session: Session | null) => void) {
  if (!supabase) {
    callback(null);
    return { unsubscribe: () => {} };
  }
  const { data: { subscription } } = supabase.auth.onAuthStateChange((_event, session) => {
    callback(session);
  });
  return subscription;
}
