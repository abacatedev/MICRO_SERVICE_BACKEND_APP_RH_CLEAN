export default function Entrar({ erro }: { erro: string }) {
  const negado = new URLSearchParams(window.location.search).get("acesso") === "negado";
  return (
    <div className="entrada">
      <h1>Pré-Censo dos Servidores</h1>
      <p>
        Diagnóstico do cadastro de servidores e dependentes da Prefeitura de Cáceres, a partir da base do SIP.
      </p>
      {negado && (
        <p className="caixa erro" role="alert">
          Esta conta Google não tem acesso. Peça o cadastro do seu e-mail ao administrador do sistema.
        </p>
      )}
      {erro && (
        <p className="caixa erro" role="alert">
          {erro}
        </p>
      )}
      <a className="botao principal" href="/rh/login">
        Entrar com Google
      </a>
      <p className="nota">O acesso é registrado. Só entra quem foi cadastrado pelo administrador.</p>
    </div>
  );
}
