import { Fragment, useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, dataHora, NaoAutenticado, numero, ROTULO_TIPO, SemPermissao, type Lista, type Ocorrencia } from "../api";

// Mesmo formato da tela do SIP: matrícula-contrato (207-1)
const matricula = (o: Ocorrencia) =>
  o.MATRICULA == null ? "" : o.CONTRATO == null ? String(o.MATRICULA) : `${o.MATRICULA}-${o.CONTRATO}`;

// "Filho(a) não emancipado menor de 21 Anos" ocupa meia tabela; o nome completo fica no detalhe
const parentescoCurto = (texto = "") => texto.split(/ (?:não|com|menor|inv)/i)[0];

const POR_PAGINA = 500;
const NA_TELA = 200;

async function carregarTudo(codigo: string): Promise<Lista> {
  const primeira = await api<Lista>(`/rh/diagnostico/${codigo}?limite=${POR_PAGINA}`);
  const itens = [...primeira.itens];
  for (let pagina = 2; itens.length < primeira.total; pagina++) {
    const mais = await api<Lista>(`/rh/diagnostico/${codigo}?limite=${POR_PAGINA}&pagina=${pagina}`);
    if (!mais.itens.length) break;
    itens.push(...mais.itens);
  }
  return { ...primeira, itens };
}

function Marcacoes({ o }: { o: Ocorrencia }) {
  const ligadas = [
    o.DEPENDENTE_IRRF === "Sim" && "IRRF",
    o.SALARIO_FAMILIA === "Sim" && "Salário família",
    o.FAIXA_IDADE === "Sim" && "Faixa de idade",
    o.UNIVERSITARIO === "Sim" && "Universitário",
    o.DEFICIENTE === "Sim" && "Deficiente",
  ].filter(Boolean) as string[];
  if (!ligadas.length) return <span className="fraco">Nenhuma</span>;
  return <>{ligadas.map((m) => <span key={m} className="marca-sip">{m}</span>)}</>;
}

function Campo({ rotulo, valor }: { rotulo: string; valor?: string | number | null }) {
  const texto = valor === null || valor === undefined || valor === "" ? null : String(valor);
  return (
    <div>
      <dt>{rotulo}</dt>
      <dd className={texto ? "" : "falta"}>{texto ?? "Não informado"}</dd>
    </div>
  );
}

function Detalhes({ o, dependente }: { o: Ocorrencia; dependente: boolean }) {
  return (
    <div className="detalhes">
      <div>
        <h3>Servidor</h3>
        <dl>
          <Campo rotulo="Registro" valor={o.REGISTRO} />
          <Campo rotulo="Matrícula e contrato" valor={matricula(o)} />
          <Campo rotulo="CPF" valor={o.CPF_SERVIDOR} />
          <Campo rotulo="Admissão" valor={o.ADMISSAO} />
          <Campo rotulo="Situação" valor={o.SITUACAO} />
          <Campo rotulo="Vínculo" valor={o.VINCULO} />
          <Campo rotulo="Cargo" valor={o.CARGO} />
          <Campo rotulo="Secretaria" valor={o.DIVISAO} />
          <Campo rotulo="Local de trabalho" valor={o.LOCAL_TRABALHO} />
          <Campo rotulo="Celular" valor={o.CELULAR} />
          <Campo rotulo="E-mail" valor={o.EMAIL} />
        </dl>
      </div>
      {dependente && (
        <div>
          <h3>Dependente (item {o.ITEM})</h3>
          <dl>
            <Campo rotulo="Nome" valor={o.DEPENDENTE} />
            <Campo rotulo="Parentesco" valor={o.PARENTESCO} />
            <Campo rotulo="Nascimento" valor={o.NASCIMENTO} />
            <Campo rotulo="Idade" valor={o.IDADE == null ? null : `${o.IDADE} anos`} />
            <Campo rotulo="CPF" valor={o.CPF_DEPENDENTE} />
            <Campo rotulo="Nome da mãe" valor={o.NOME_MAE} />
            <Campo rotulo="Documentos preenchidos" valor={o.DOCUMENTOS} />
            <Campo rotulo="Data de entrega" valor={o.DATA_ENTREGA} />
            <Campo rotulo="Dependente IRRF?" valor={o.DEPENDENTE_IRRF} />
            <Campo rotulo="Salário Família" valor={o.SALARIO_FAMILIA} />
            <Campo rotulo="Considerar para Faixa de Idade?" valor={o.FAIXA_IDADE} />
            <Campo rotulo="Universitário?" valor={o.UNIVERSITARIO} />
            <Campo rotulo="Deficiente Físico?" valor={o.DEFICIENTE} />
          </dl>
        </div>
      )}
    </div>
  );
}

export default function ListaDaRegra({ aoExpirar }: { aoExpirar: () => void }) {
  const { codigo = "" } = useParams();
  const [lista, setLista] = useState<Lista | null>(null);
  const [erro, setErro] = useState("");
  const [busca, setBusca] = useState("");
  const [aberta, setAberta] = useState<string | null>(null);

  useEffect(() => {
    setLista(null);
    setErro("");
    setAberta(null);
    carregarTudo(codigo)
      .then(setLista)
      .catch((e) => {
        if (e instanceof NaoAutenticado) aoExpirar();
        else if (e instanceof SemPermissao) setErro("Seu perfil vê só o painel. A lista com nomes é restrita ao RH.");
        else setErro(e instanceof Error ? e.message : "Falha.");
      });
  }, [codigo]); // eslint-disable-line react-hooks/exhaustive-deps

  const filtrados = useMemo(() => {
    if (!lista) return [];
    const termo = busca.trim().toUpperCase();
    if (!termo) return lista.itens;
    const campos = (o: Ocorrencia) => [
      o.SERVIDOR, o.DEPENDENTE, o.DIVISAO, o.LOCAL_TRABALHO, o.CARGO, o.REGISTRO, matricula(o),
      o.CPF_SERVIDOR, o.CPF_DEPENDENTE,
    ];
    const soNumeros = termo.replace(/\D/g, "");
    return lista.itens.filter((o) =>
      campos(o).some((c) => {
        const valor = (c ?? "").toUpperCase();
        return valor.includes(termo) || (soNumeros.length >= 3 && valor.replace(/\D/g, "").includes(soNumeros));
      }),
    );
  }, [lista, busca]);

  if (erro) return <p className="caixa erro" role="alert">{erro} <Link to="/">Voltar ao painel</Link></p>;
  if (!lista) return <p className="aviso">Carregando a lista…</p>;

  const { regra } = lista;
  const dependente = regra.alvo === "dependente";
  const colunas = dependente ? 9 : 5;
  return (
    <>
      <p className="trilha nao-imprimir"><Link to="/">Painel</Link> / {ROTULO_TIPO[regra.tipo]}</p>
      <section className="abertura">
        <h1>{regra.titulo}</h1>
        <p className="texto">{regra.descricao}</p>
        <p className="caixa orientacao"><strong>O que fazer:</strong> {regra.orientacao}</p>
        <p className="rodape-abertura">
          {numero(lista.servidores)} servidores, {numero(lista.total)} ocorrências. Leitura de {dataHora(lista.gerado_em)}.
        </p>
      </section>

      <div className="ferramentas nao-imprimir">
        <label>
          <span className="so-leitor">Buscar na lista</span>
          <input
            type="search"
            placeholder="Buscar por nome, registro, matrícula, CPF ou secretaria"
            value={busca}
            onChange={(e) => setBusca(e.target.value)}
          />
        </label>
        <a className="botao principal" href={`/rh/diagnostico/${regra.codigo}?formato=csv`}>Baixar planilha (CSV)</a>
      </div>

      {filtrados.length === 0 ? (
        <p className="aviso">{busca ? "Nenhuma linha combina com a busca." : "Nenhuma ocorrência nesta regra."}</p>
      ) : (
        <div className="rolagem">
          <table className="livro denso">
            <thead>
              <tr>
                <th>Registro</th>
                <th>Matrícula</th>
                <th>Servidor</th>
                <th>Secretaria</th>
                {dependente && <th>Dependente</th>}
                {dependente && <th>Nascimento</th>}
                {dependente && <th>CPF</th>}
                {dependente && <th>Marcações no SIP</th>}
                <th>{dependente ? "Detalhe" : "Contato e detalhe"}</th>
              </tr>
            </thead>
            <tbody>
              {filtrados.slice(0, NA_TELA).map((o, i) => {
                const chave = `${o.REGISTRO}-${o.ITEM ?? 0}-${i}`;
                const expandida = aberta === chave;
                return (
                  <Fragment key={chave}>
                    <tr className={expandida ? "aberta" : ""}>
                      <td className="registro">{o.REGISTRO}</td>
                      <td className="sem-quebra">{matricula(o)}</td>
                      <td>{o.SERVIDOR}<span className="fraco bloco">{o.VINCULO}</span></td>
                      <td>{o.DIVISAO}<span className="fraco bloco">{o.LOCAL_TRABALHO}</span></td>
                      {dependente && (
                        <td>{o.DEPENDENTE}<span className="fraco bloco" title={o.PARENTESCO}>{parentescoCurto(o.PARENTESCO)}</span></td>
                      )}
                      {dependente && (
                        <td className="sem-quebra">{o.NASCIMENTO}<span className="fraco bloco">{o.IDADE == null ? "" : `${o.IDADE} anos`}</span></td>
                      )}
                      {dependente && (
                        <td className="sem-quebra">{o.CPF_DEPENDENTE || <span className="falta">Sem CPF</span>}</td>
                      )}
                      {dependente && <td><Marcacoes o={o} /></td>}
                      <td>
                        {!dependente && <span className="fraco bloco">{[o.CELULAR, o.EMAIL].filter(Boolean).join(" | ")}</span>}
                        {o.DETALHE}
                        <button
                          className="botao discreto ver"
                          aria-expanded={expandida}
                          onClick={() => setAberta(expandida ? null : chave)}
                        >
                          {expandida ? "Fechar" : "Ver tudo"}
                        </button>
                      </td>
                    </tr>
                    {expandida && (
                      <tr className="linha-detalhes">
                        <td colSpan={colunas}><Detalhes o={o} dependente={dependente} /></td>
                      </tr>
                    )}
                  </Fragment>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
      {filtrados.length > NA_TELA && (
        <p className="nota">
          Mostrando {NA_TELA} de {numero(filtrados.length)} linhas. Use a busca para refinar, ou baixe a planilha para ver todas.
        </p>
      )}
    </>
  );
}
