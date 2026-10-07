import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// Em desenvolvimento, o Vite repassa as rotas da API para o backend.
// Assim navegador, frontend e API ficam na mesma origem e o cookie de sessão funciona.
const api = process.env.API_TARGET ?? "http://localhost:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: Object.fromEntries(
      ["/rh", "/auth", "/oauth", "/.well-known"].map((rota) => [rota, { target: api, changeOrigin: false }]),
    ),
  },
});
