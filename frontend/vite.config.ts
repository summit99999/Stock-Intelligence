import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  return {
    plugins: [react()],
    envPrefix: ["VITE_", "NEXT_PUBLIC_", "PUBLIC_"],
    define: {
      "import.meta.env.API_BASE_URL": JSON.stringify(env.API_BASE_URL || env.VITE_API_BASE_URL || ""),
    },
    resolve: {
      preserveSymlinks: true,
    },
    build: {
      rollupOptions: {
        output: {
          manualChunks: {
            charts: ["lightweight-charts"],
            vendor: ["react", "react-dom"],
            supabase: ["@supabase/supabase-js"],
          },
        },
      },
    },
  };
});
