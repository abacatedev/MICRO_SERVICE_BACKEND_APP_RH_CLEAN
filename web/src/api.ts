// Toda conversa com o backend passa por aqui. O frontend não guarda regra de negócio:
// títulos, gravidades e números vêm sempre da API.

export class NaoAutenticado extends Error {}
export class SemPermissao extends Error {}

export async function api<T>(caminho: string): Promise<T> {
  const resposta = await fetch(caminho, { credentials: "same-origin", headers: { Accept: "application/json" } });
  if (resposta.status === 401) throw new NaoAutenticado();
  if (resposta.status === 403) throw new SemPermissao();
  if (!resposta.ok) throw new Error(`A consulta falhou (${resposta.status}). Tente de novo em instantes.`);
  return resposta.json() as Promise<T>;
}

export type Usuario = {
  email: string;
  name: string;
  roles: string[];
  permissions: string[];
  sessao_expira_em: string | null;
};

export type Tipo = "erro" | "alerta" | "recadastro" | "conferencia" | "indicador";

export type Regra = {
  codigo: string;
  titulo: string;
  tipo: Tipo;
  alvo: "dependente" | "servidor";
  descricao: string;
  orientacao: string;
  servidores: number;
  ocorrencias: number;
};

export type Resumo = { vinculos: number; com_erro: number; com_alerta: number; sem_pendencia: number };

export type Painel = {
  gerado_em: string;
  universo: { vinculos: number; dependentes: number; situacoes: string[] };
  resumo: Resumo;
  regras: Regra[];
};

export type Divisao = Resumo & { divisao: string };

export type Ocorrencia = {
  REGISTRO: string;
  MATRICULA: number | null;
  CONTRATO: number | null;
  SERVIDOR: string;
  CPF_SERVIDOR: string;
  ADMISSAO: string;
  SITUACAO: string | null;
  VINCULO: string | null;
  CARGO: string | null;
  DIVISAO: string | null;
  LOCAL_TRABALHO: string | null;
  CELULAR: string;
  EMAIL: string;
  ITEM?: number;
  DEPENDENTE?: string;
  PARENTESCO?: string;
  NASCIMENTO?: string;
  IDADE?: number | null;
  CPF_DEPENDENTE?: string;
  DEPENDENTE_IRRF?: string;
  SALARIO_FAMILIA?: string;
  FAIXA_IDADE?: string;
  UNIVERSITARIO?: string;
  DEFICIENTE?: string;
  DOCUMENTOS?: string;
  DATA_ENTREGA?: string;
  NOME_MAE?: string;
  DETALHE: string;
};

export type Lista = {
  regra: Omit<Regra, "servidores" | "ocorrencias">;
  gerado_em: string;
  total: number;
  servidores: number;
  itens: Ocorrencia[];
};

export const ROTULO_TIPO: Record<Tipo, string> = {
  erro: "Erro",
  alerta: "Alerta",
  recadastro: "Recadastro",
  conferencia: "Conferência",
  indicador: "Indicador",
};

export const numero = (n: number) => n.toLocaleString("pt-BR");
export const porcento = (parte: number, todo: number) =>
  todo ? `${((parte / todo) * 100).toLocaleString("pt-BR", { maximumFractionDigits: 1 })}%` : "0%";
export const dataHora = (iso: string) =>
  new Date(iso).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" });
