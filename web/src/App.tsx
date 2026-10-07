import { useEffect, useState } from "react";
import { Link, Route, Routes } from "react-router-dom";
import { api, NaoAutenticado, type Usuario } from "./api";
import Entrar from "./pages/Entrar";
import Painel from "./pages/Painel";
import ListaDaRegra from "./pages/ListaDaRegra";

const PERFIL: Record<string, string> = { admin: "Administrador", rh: "Recursos Humanos", consulta: "Consulta" };

export default function App() {
  const [usuario, setUsuario] = useState<Usuario | null | undefined>(undefined);
  const [erro, setErro] = useState("");

  useEffect(() => {
    api<Usuario>("/rh/me")
      .then(setUsuario)
      .catch((e) => {
        if (!(e instanceof NaoAutenticado)) setErro(e instanceof Error ? e.message : "Falha ao carregar.");
        setUsuario(null);
      });
  }, []);

  if (usuario === undefined) return <p className="aviso">Carregando…</p>;
  if (usuario === null) return <Entrar erro={erro} />;

  const sair = () => setUsuario(null);
  return (
    <>
      <header className="topo">
        <Link to="/" className="marca">
          Pré-Censo dos Servidores
          <span>Prefeitura de Cáceres</span>
        </Link>
        <div className="conta">
          <div>
            <strong>{usuario.name}</strong>
            <span>{usuario.roles.map((r) => PERFIL[r] ?? r).join(", ")}</span>
          </div>
          <a className="botao discreto" href="/rh/logout">
            Sair
          </a>
        </div>
      </header>
      <main>
        <Routes>
          <Route path="/" element={<Painel usuario={usuario} aoExpirar={sair} />} />
          <Route path="/regra/:codigo" element={<ListaDaRegra aoExpirar={sair} />} />
          <Route path="*" element={<p className="aviso">Página não encontrada. <Link to="/">Voltar ao painel</Link></p>} />
        </Routes>
      </main>
    </>
  );
}
