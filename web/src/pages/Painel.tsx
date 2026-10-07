import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  api, dataHora, NaoAutenticado, numero, porcento, ROTULO_TIPO,
  type Divisao, type Painel as DadosPainel, type Regra, type Resumo, type Tipo, type Usuario,
} from "../api";

const GRUPOS: { tipos: Tipo[]; titulo: string; texto: string }[] = [
  { tipos: ["erro"], titulo: "Erros", texto: "Cadastro incorreto ou incompleto, que precisa de correção." },
  { tipos: ["alerta", "recadastro"], titulo: "Alertas", texto: "Vale conferir com o servidor." },
  { tipos: ["conferencia", "indicador"], titulo: "Para acompanhar", texto: "Não são pendências; ajudam a planejar o Censo." },
];

function Regua({ r, rotulos = false }: { r: Resumo; rotulos?: boolean }) {
  const partes = [
    { classe: "erro", valor: r.com_erro, nome: "com erro" },
    { classe: "alerta", valor: r.com_alerta, nome: "só com alerta" },
    { classe: "ok", valor: r.sem_pendencia, nome: "sem pendência" },
  ];
  return (
    <div>
      <div className="regua" role="img" aria-label={partes.map((p) => `${numero(p.valor)} ${p.nome}`).join(", ")}>
        {partes.map((p) => p.valor > 0 && <span key={p.classe} className={p.classe} style={{ flexGrow: p.valor }} />)}
      </div>
      {rotulos && (
        <ul className="legenda">
          {partes.map((p) => (
            <li key={p.classe}>
              <i className={p.classe} />
              <strong>{numero(p.valor)}</strong> {p.nome} <span>{porcento(p.valor, r.vinculos)}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function LinhaDaRegra({ regra, maior, podeListar }: { regra: Regra; maior: number; podeListar: boolean }) {
  const titulo = podeListar && regra.servidores > 0
    ? <Link to={`/regra/${regra.codigo}`}>{regra.titulo}</Link>
    : regra.titulo;
  return (
    <tr>
      <td>
        <div className="titulo-regra">
          <span className={`etiqueta ${regra.tipo}`}>{ROTULO_TIPO[regra.tipo]}</span>
          {titulo}
        </div>
        <p className="descricao">{regra.descricao}</p>
      </td>
      <td className="barra-celula">
        <span className={`barra ${regra.tipo}`} style={{ width: `${maior ? (regra.servidores / maior) * 100 : 0}%` }} />
      </td>
      <td className="n">{numero(regra.servidores)}</td>
      <td className="n fraco">{numero(regra.ocorrencias)}</td>
    </tr>
  );
}

export default function Painel({ usuario, aoExpirar }: { usuario: Usuario; aoExpirar: () => void }) {
  const [dados, setDados] = useState<DadosPainel | null>(null);
  const [divisoes, setDivisoes] = useState<Divisao[]>([]);
  const [erro, setErro] = useState("");
  const [carregando, setCarregando] = useState(true);
  const podeListar = usuario.permissions.includes("rh:diagnostico:listar");

  const carregar = (atualizar = false) => {
    setCarregando(true);
    setErro("");
    api<DadosPainel>(`/rh/diagnostico${atualizar ? "?atualizar=true" : ""}`)
      .then((painel) => {
        setDados(painel);
        return api<Divisao[]>("/rh/diagnostico/por-divisao").then(setDivisoes);
      })
      .catch((e) => (e instanceof NaoAutenticado ? aoExpirar() : setErro(e instanceof Error ? e.message : "Falha.")))
      .finally(() => setCarregando(false));
  };
  useEffect(carregar, []); // eslint-disable-line react-hooks/exhaustive-deps

  if (erro) return <p className="caixa erro" role="alert">{erro} <button className="botao discreto" onClick={() => carregar()}>Tentar de novo</button></p>;
  if (!dados) return <p className="aviso">Lendo o cadastro no SIP. A primeira leitura leva alguns segundos…</p>;

  const { resumo, universo } = dados;
  const maior = Math.max(...dados.regras.map((r) => r.servidores), 1);

  return (
    <>
      <section className="abertura">
        <h1>
          {numero(resumo.com_erro)} de {numero(resumo.vinculos)} vínculos ativos têm erro de cadastro
        </h1>
        <Regua r={resumo} rotulos />
        <p className="rodape-abertura">
          {numero(universo.dependentes)} dependentes analisados. Leitura de {dataHora(dados.gerado_em)}.
          <span className="acoes nao-imprimir">
            <button className="botao discreto" onClick={() => carregar(true)} disabled={carregando}>
              {carregando ? "Atualizando…" : "Atualizar leitura"}
            </button>
            <button className="botao discreto" onClick={() => window.print()}>Imprimir resumo</button>
          </span>
        </p>
      </section>

      {GRUPOS.map((grupo) => {
        const regras = dados.regras.filter((r) => grupo.tipos.includes(r.tipo));
        if (!regras.length) return null;
        return (
          <section key={grupo.titulo}>
            <h2>{grupo.titulo}</h2>
            <p className="sub">{grupo.texto}</p>
            <table className="livro">
              <thead>
                <tr>
                  <th>Regra</th>
                  <th aria-hidden="true" />
                  <th className="n">Servidores</th>
                  <th className="n">Ocorrências</th>
                </tr>
              </thead>
              <tbody>
                {regras.map((r) => <LinhaDaRegra key={r.codigo} regra={r} maior={maior} podeListar={podeListar} />)}
              </tbody>
            </table>
          </section>
        );
      })}

      {divisoes.length > 0 && (
        <section>
          <h2>Por secretaria</h2>
          <p className="sub">Vínculos de cada secretaria, da que tem mais erros para a que tem menos.</p>
          <table className="livro">
            <thead>
              <tr>
                <th>Secretaria</th>
                <th>Situação dos vínculos</th>
                <th className="n">Com erro</th>
                <th className="n">Vínculos</th>
              </tr>
            </thead>
            <tbody>
              {divisoes.map((d) => (
                <tr key={d.divisao}>
                  <td>{d.divisao}</td>
                  <td className="regua-celula"><Regua r={d} /></td>
                  <td className="n">{numero(d.com_erro)} <span className="fraco">{porcento(d.com_erro, d.vinculos)}</span></td>
                  <td className="n fraco">{numero(d.vinculos)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}
      <p className="nota">
        Os números medem o cadastro do SIP, não o que a folha paga ou deduz. Universo: empresa 001, situações{" "}
        {universo.situacoes.join(" e ")}.
      </p>
    </>
  );
}
