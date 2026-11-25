# Forja — Construtor de Sites e Apps com IA (cérebro OpenRouter)

Uma plataforma em que a pessoa descreve no chat o site ou app que quer, de qualquer tipo, e a IA cria o projeto completo seguindo o pedido. O formato é o mesmo da Emergent: React no front-end e Python (FastAPI) no back-end.
Tudo fica salvo, pode ser importado do GitHub e enviado de volta. O "cérebro" é a OpenRouter (sua chave ou a do próprio usuário), e um painel admin controla usuários, modelos e custos.

## Para quem é
- **Você (dono/admin):** controla quem usa, os modelos liberados, os gastos e os limites.
- **Seus usuários:** pessoas que querem criar ou continuar sites e apps conversando com a IA.

## Funcionalidades principais e experiência
**Construtor (usuário)**
- Login com Google.
- Lista de projetos: criar do zero, **importar do GitHub**, renomear, abrir, excluir.
- Tela de trabalho: **chat**, **árvore de arquivos + editor de código** e **prévia ao vivo** do site.
- A IA gera projetos com várias páginas e arquivos:
  - `frontend/`: React;
  - `backend/`: Python FastAPI, com `requirements.txt` e `.env.example`;
  - `README.md`.
- A resposta aparece em tempo real, e os arquivos vão surgindo na árvore.

**1. Edição por blocos (busca e substitui)**
- A IA trabalha com ferramentas, como um agente: listar arquivos, ler um arquivo (inteiro ou só algumas linhas), buscar texto no projeto, **substituir um trecho**, criar um arquivo novo e apagar um arquivo.
- Para mudar um arquivo existente, ela envia **apenas o trecho antigo e o trecho novo**. Reescrever o arquivo inteiro só é permitido em arquivos novos ou muito pequenos.
- Se um trecho não for encontrado, a IA recebe o erro e tenta de novo, sem corromper o arquivo.
- No chat, cada alteração aparece como um cartão "arquivo X: +3 / −1 linhas", e ao clicar dá para ver a diferença (verde/vermelho).
- Isso economiza tokens da OpenRouter e evita respostas longas que estouram o tempo limite.

**2. Upload de arquivos e assets**
- Botão "Enviar arquivos" e arrastar-e-soltar direto na árvore (em qualquer pasta). Aceita .html, .css, .js, .json, .md, .txt, .py e imagens (png, jpg, svg, webp).
- Os arquivos **não são colados no chat**. A IA só recebe um resumo curto:
  - HTML: título e estrutura de seções;
  - JSON: chaves e tamanho;
  - código: funções e linhas;
  - imagens: nome, formato, dimensões e caminho.
- Quando precisa de mais detalhe, a IA lê trechos específicos com as ferramentas.
- As imagens enviadas podem ser usadas no site gerado e aparecem na prévia.

**3. Importar do GitHub**
- Ao criar um projeto, a opção "Importar do GitHub" lista os repositórios da conta conectada, inclusive privados (ex.: `projeto-pro-frotas-001`), com escolha do branch.
- O conteúdo é puxado para a árvore de arquivos. Ficam de fora pastas pesadas e geradas (`node_modules`, `build`, `dist`, `.git`, ambientes Python) e arquivos acima de 5 MB.
- A IA recebe um mapa resumido do repositório para continuar de onde você parou.
- "Enviar para o GitHub" atualiza o mesmo repositório com um commit, ou cria um repositório novo.

**4. Modelos e chave própria**
- Seletor rápido no chat, salvo por projeto, para trocar de modelo a qualquer momento.
- Já vêm configurados `qwen/qwen3-coder-next` (rápido) e `qwen/qwen3-coder` (tarefas pesadas), e o admin pode liberar outros.
- Em Configurações, o usuário pode colocar **a própria chave da OpenRouter**. Com ela, o uso sai da conta dele e não tem o limite diário da plataforma. Sem ela, ele usa a sua chave, com limite.
- A chave do usuário fica guardada criptografada, nunca é mostrada de volta e pode ser removida a qualquer momento.

**Também no construtor**
- Edição manual no editor, histórico de versões (voltar para qualquer uma), download .zip e tudo salvo automaticamente.

**Painel admin (você)**
- Visão geral: usuários, projetos, mensagens e custo total em dólares (valor real informado pela OpenRouter), separando o que saiu da sua chave do que saiu da chave dos usuários.
- Usuários: lista, gasto, quem usa chave própria, bloquear/desbloquear.
- Modelos: liberar ou ocultar modelos da OpenRouter e definir o padrão.
- Limite diário por usuário (vale só para quem usa a sua chave).
- Histórico de uso: modelo, tokens e custo de cada chamada.

## Fluxo do usuário
1. Entra com Google e conecta o GitHub (opcional) e a própria chave da OpenRouter (opcional) em Configurações.
2. "Novo projeto": começa do zero ou importa um repositório.
3. Escolhe o modelo, descreve o que quer e envia arquivos se precisar.
4. A IA cria ou edita por trechos, e a prévia é atualizada.
5. Revisa as mudanças, volta versões se preciso e envia ao GitHub ou baixa o .zip.

## Sensação visual (UI/UX)
Ferramenta profissional escura, no estilo de editor de código: fundo escuro sólido, uma cor de destaque forte, tipografia marcante e animações suaves quando arquivos surgem e trechos mudam. O foco fica no chat, no código e na prévia.

## Fases de implementação
**Fase 1 — MVP (construída agora)**
Tudo acima: login, projetos, agente com edição por trechos, upload com resumos, importar e enviar ao GitHub, seletor de modelo por projeto, chave própria opcional, prévia do front-end, versões, .zip e painel admin.

**Fase 2**
- Rodar o back-end Python em ambiente isolado, para a prévia funcionar com API e banco reais.
- Publicar o site em um link público.
- Abrir pull requests no GitHub em vez de enviar direto para o branch.

**Fase 3**
- Agente que testa e corrige o projeto sozinho.
- Templates por tipo de site.
- Planos pagos para os seus usuários.

## Premissas (decididas sem perguntar)
- **Na Fase 1, a prévia ao vivo mostra só o front-end (React).** O Python é gerado, editado, salvo e sincronizado com o GitHub, mas não roda dentro da plataforma.
- Os modelos usados precisam suportar ferramentas (function calling) na OpenRouter. Os dois Qwen Coder pedidos suportam, e o painel só deixa liberar modelos compatíveis.
- Repositórios importados muito grandes são limitados a cerca de 2.000 arquivos de texto. O que ficar de fora é avisado na tela.
- O envio ao GitHub vai direto para o branch escolhido, com uma mensagem de commit gerada a partir das mudanças. O usuário pode editar essa mensagem.
- Arquivos enviados e imagens ficam em armazenamento de arquivos próprio (não no banco), com limite de 10 MB por arquivo.
- GitHub conectado por token de acesso pessoal do usuário, guardado criptografado.
- Login com Google gerenciado pela Emergent, com o seu e-mail como admin (pedido na hora de construir).
- Sua chave da OpenRouter é pedida em um cartão seguro na hora de construir. Limite diário padrão para quem usa a sua chave: US$ 2, alterável no painel.
- Projetos são privados: o admin vê uso e custos, não o conteúdo.
- Interface em português.
