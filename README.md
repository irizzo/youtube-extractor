# YouTube Video Metadata & Comments Extractor

[Português](#pt-br) · [English](#en-us)

## PT-BR

Um pipeline configurável que coleta **vídeos** e seus **comentários** pela YouTube Data API v3 e os armazena como datasets JSONL, prontos para análise de texto.

Uma execução tem duas etapas:

1. **Vídeos** — faz uma busca no YouTube para cada consulta, complementa cada resultado com a descrição completa e a duração, descarta duplicatas (e, opcionalmente, Shorts) e grava `videos.jsonl`.
2. **Comentários** — relê `videos.jsonl` em streaming, busca os comentários de primeiro nível de cada vídeo, limpa o texto e grava `comments.jsonl`.

As duas etapas salvam **checkpoints**: se uma execução parar no meio (cota esgotada, erro de rede, `Ctrl+C`), basta executá-la de novo para retomar de onde parou, sem baixar outra vez o que você já tem.

### Instalação

1. **Instale o uv**

Siga os passos de instalação do [uv](https://docs.astral.sh/uv/) (gerenciador de ambientes Python).

2. **Sincronize as dependências**

Na raiz do projeto, execute:

```bash
uv sync
```

3. **Obtenha sua chave da YouTube Data API**

Acesse o Google Cloud Console e siga os passos para criar um projeto e obter sua **API KEY**. Em seguida, crie um arquivo `.env` na raiz do projeto e adicione sua API KEY na variável `YT_API_KEY`, como no arquivo de exemplo `.env.example`.

### Execução

#### Configuração

Você pode definir a configuração da busca no YouTube alterando os parâmetros abaixo. Outros parâmetros nativos de busca estão na página de documentação do método [`search.list()`](https://developers.google.com/youtube/v3/docs/search/list), mas **ainda não foram implementados**.

##### `youtube_search_config` — o que coletar

| Parâmetro | Obrigatório | Padrão | Descrição |
| --- | --- | --- | --- |
| `youtube_api_key` | sim | — | Lido de `YT_API_KEY` no seu `.env`. A execução falha imediatamente se ele estiver ausente. |
| `queries` | não | `[""]` | Lista de termos de busca. **Uma busca é feita para cada item**, e os resultados de todas vão para o mesmo arquivo de saída. |
| `remove_short_videos` | não | `False` | `True` descarta vídeos com menos de 3 minutos ou com `#short` na descrição. |
| `language` | não | `"en"` | Código ISO 639-1 enviado como `relevanceLanguage`. Ele *favorece* resultados nesse idioma, mas não os filtra de forma estrita. |
| `published_after` | não | — | Timestamp RFC 3339 (`"2026-01-01T00:00:00Z"`). Só são retornados vídeos publicados depois desse momento. |
| `results_per_search` | não | `50` | Vídeos solicitados **por consulta**, buscados em páginas de 50. O YouTube interrompe a paginação de uma busca em cerca de 500 resultados, então a etapa termina antes quando a API não retorna uma próxima página. |
| `max_comments_per_video` | não | `50000` | Limite de comentários coletados por vídeo. É verificado entre páginas de 100, então o teto efetivo é o próximo múltiplo de 100. |

As consultas aceitam os operadores de busca do YouTube: `|` significa OU, um espaço ` ` significa E, aspas buscam uma frase exata e `-` exclui um termo. O exemplo incluído

```python
"(eleições|bolsonaro|lula|'segundo turno') (brasil)"
```

encontra vídeos que mencionam qualquer um desses quatro termos E "brasil".

##### `dir_config` — onde gravar

| Parâmetro | Padrão | Descrição |
| --- | --- | --- |
| `current_results_dir` | `"data"` | Diretório das saídas e dos checkpoints. É criado se não existir. |
| `videos_output_filename` | `"videos.jsonl"` | Vídeos coletados. |
| `videos_checkpoint_filename` | `"videos_checkpoint.json"` | Consultas já concluídas. |
| `comments_output_filename` | `"comments.jsonl"` | Comentários coletados. |
| `comments_checkpoint_filename` | `"comments_checkpoint.json"` | Vídeos cujos comentários já foram coletados. |

Como os arquivos são sempre gravados em modo de **acréscimo** (append), **dê a cada coleta seu próprio `current_results_dir`** (por exemplo, `data/extraction/20261015_111836`) quando quiser um dataset separado, e não a continuação do anterior.

#### Executar

Na raiz do projeto:

```bash
uv run main.py
```

O progresso é exibido no terminal e gravado em um arquivo de log dentro de `current_results_dir`, nomeado com o momento em que a execução começou — `extraction_20261018_114459.log` (log rotativo de 5 MB, com dois backups). Cada execução ganha seu próprio arquivo, então os logs de execuções anteriores nunca são sobrescritos.

### Saída

```
data/
├── videos.jsonl                      # um vídeo por linha
├── videos_checkpoint.json            # ["consulta já concluída", ...]
├── comments.jsonl                    # um comentário por linha
├── comments_checkpoint.json          # ["video_id já concluído", ...]
└── extraction_20261018_114459.log    # um log por execução
```

#### `videos.jsonl`

| Campo | Descrição |
| --- | --- |
| `video_id` | ID do vídeo no YouTube. |
| `video_title` | Título original. |
| `video_description` | Descrição completa, como retornada pela API. |
| `published_at` | Data e hora de publicação (RFC 3339). |
| `channel_title` | Nome de exibição do canal. |
| `channel_id` | ID do canal, usado depois para descartar os comentários do próprio canal. |
| `video_duration` | Duração em ISO 8601, por exemplo `PT5M1S`. |
| `clean_title` | Título pré-processado (`null` se nada restou após a limpeza). |
| `clean_description` | Descrição pré-processada (`null` se vazia ou se nada restou após a limpeza). |

#### `comments.jsonl`

| Campo | Descrição |
| --- | --- |
| `video_id` | Vídeo ao qual o comentário pertence. |
| `comment_id` | ID do comentário no YouTube. |
| `raw_text` | Texto original do comentário. |
| `comment_likes` | Número de curtidas no momento da coleta. |
| `comment_replies` | Número de respostas (as respostas em si não são coletadas). |
| `clean_text` | Texto pré-processado. |

#### O que é filtrado

- Vídeos já presentes em `videos.jsonl`, para que termos repetidos entre consultas nunca dupliquem uma linha.
- Vídeos com menos de 3 minutos ou marcados com `#short`, quando `remove_short_videos` é `True`.
- Comentários escritos pelo próprio canal do vídeo.
- Comentários que ficam vazios após a limpeza.
- Respostas — só são coletados comentários de primeiro nível, limitados a `max_comments_per_video`.

Vídeos com comentários desativados, ou inacessíveis por outro motivo, são registrados no log e ignorados; a execução continua.

#### Limpeza de texto

Nos campos `clean_*`, primeiro as entidades HTML são decodificadas (`&amp;` → `&`, `&#39;` → `'`); depois são removidos emojis, tags HTML, URLs, marcações de tempo (`12:34`) e caracteres de seta; letras e pontuação repetidas em excesso são reduzidas (`loooool` → `lool`); e os espaços em branco são condensados.

O texto original é sempre mantido ao lado e nunca é modificado — `video_title` e `raw_text` ficam exatamente como a API os retornou, inclusive com as entidades escapadas. Os resultados de busca chegam com escape HTML, então é normal ver `&#39;` em `video_title`, mesmo que `clean_title` mostre `'`. Assim, você sempre pode refazer a limpeza a partir do texto bruto armazenado, sem coletar de novo.

### Retomar e recomeçar

Os arquivos de saída são gravados em modo de acréscimo, e os checkpoints são salvos após cada consulta (vídeos) e após cada vídeo (comentários), então é seguro repetir uma execução interrompida.

- **Adicionar uma nova consulta** — acrescente-a a `queries` e execute de novo. As consultas listadas em `videos_checkpoint.json` são puladas, então só a nova gasta cota.
- **Começar um dataset do zero** — aponte `current_results_dir` para um novo diretório, ou apague os quatro arquivos do diretório atual.
- **Cuidado ao apagar só um checkpoint** — remover `videos_checkpoint.json` refaz as buscas, mas a verificação de duplicatas continua protegendo `videos.jsonl`. Remover `comments_checkpoint.json` não tem essa proteção: todos os comentários são buscados e acrescentados uma segunda vez.

O diretório `data/` inteiro está no `.gitignore`, então os datasets coletados nunca entram no repositório. Faça backup deles por conta própria — nada no git os protege.

### Cota da API

Por padrão, a YouTube Data API concede 10.000 unidades por dia a cada projeto:

| Chamada | Custo | Feita uma vez por |
| --- | --- | --- |
| `search.list` | 100 unidades | página de até 50 vídeos |
| `videos.list` | 1 unidade | lote de até 50 vídeos (durações e descrições completas) |
| `commentThreads.list` | 1 unidade | página de até 100 comentários |

A etapa de vídeos é a mais cara: `results_per_search: 200` com uma única consulta custa cerca de 404 unidades, enquanto coletar 100.000 comentários custa por volta de 1.000. Quando a cota acaba, a API retorna `403 quotaExceeded` — os checkpoints permitem retomar a execução no dia seguinte.

### Estrutura do projeto

```
main.py                              # ponto de entrada: etapa de vídeos, depois a de comentários
src/
├── config.py                        # todas as configurações do usuário
├── extraction/
│   ├── extraction_pipeline.py       # orquestração, checkpoints, deduplicação
│   ├── yt_videos_retrieval.py       # search.list + videos.list, filtro de Shorts
│   └── yt_comments_retrieval.py     # commentThreads.list, filtro de comentários
└── utils/
    ├── api.py                       # cliente compartilhado da API, requisições com tratamento de cota
    ├── handle_config.py             # aplica os padrões, valida a chave da API, monta os caminhos
    ├── helpers.py                   # streaming de JSONL e pré-processamento de texto
    └── logger.py                    # logger no console + arquivo de log rotativo
```

---

## EN-US

A configurable pipeline that collects **videos** and their **comments** from the YouTube Data API v3 and stores them as JSONL datasets, ready for text analysis.

A run has two stages:

1. **Videos** — runs one YouTube search per query, enriches each hit with its full description and duration, discards duplicates (and optionally Shorts), and writes `videos.jsonl`.
2. **Comments** — streams `videos.jsonl` back in, fetches the top-level comments of every video, cleans the text, and writes `comments.jsonl`.

Both stages are **checkpointed**: if a run stops halfway (quota exhausted, network error, `Ctrl+C`), running it again resumes where it stopped instead of re-downloading what you already have.

### Set Up

1. **Install uv**

Follow the steps to install [uv](https://docs.astral.sh/uv/) (Python environment manager).

2. **Sync the dependencies**

At the root of the project, run:

```bash
uv sync
```

3. **Get your YouTube Data API KEY**

Go to the Google Cloud Console and follow the steps to create a project and get your **API KEY**. Then create a `.env` file in the root of the project, and add your API KEY under the `YT_API_KEY` var, as in the `.env.example` example file.

### Running

#### Config

You can set the YouTube search configuration by changing the following parameters. Other native search parameters can be found on the [`search.list()`](https://developers.google.com/youtube/v3/docs/search/list) method's documentation page, but are **not yet implemented**.

##### `youtube_search_config` — what to collect

| Parameter | Required | Default | Description |
| --- | --- | --- | --- |
| `youtube_api_key` | yes | — | Read from `YT_API_KEY` in your `.env`. The run fails immediately if it is missing. |
| `queries` | no | `[""]` | List of search strings. **One search is run per entry**, and the results of all of them land in the same output file. |
| `remove_short_videos` | no | `False` | `True` discards videos shorter than 3 minutes or with `#short` in the description. |
| `language` | no | `"en"` | ISO 639-1 code sent as `relevanceLanguage`. It *biases* results toward that language; it does not hard-filter them. |
| `published_after` | no | — | RFC 3339 timestamp (`"2026-01-01T00:00:00Z"`). Only videos published after this moment are returned. |
| `results_per_search` | no | `50` | Videos requested **per query**, fetched in pages of 50. YouTube stops paginating a single search at roughly 500 results, so the stage ends early when the API returns no next page. |
| `max_comments_per_video` | no | `50000` | Upper bound on comments collected per video. Checked between pages of 100, so the effective ceiling is the next multiple of 100. |

Queries accept YouTube's search operators: `|` means OR, a space ` ` means AND, quotes match an exact phrase, and `-` excludes a term. The shipped example

```python
"(eleições|bolsonaro|lula|'segundo turno') (brasil)"
```

matches videos mentioning any of those four terms AND "brasil".

##### `dir_config` — where to write it

| Parameter | Default | Description |
| --- | --- | --- |
| `current_results_dir` | `"data"` | Directory for the outputs and checkpoints. Created if it does not exist. |
| `videos_output_filename` | `"videos.jsonl"` | Collected videos. |
| `videos_checkpoint_filename` | `"videos_checkpoint.json"` | Queries already finished. |
| `comments_output_filename` | `"comments.jsonl"` | Collected comments. |
| `comments_checkpoint_filename` | `"comments_checkpoint.json"` | Videos whose comments are already collected. |

Since every file is **appended** to, **give each collection its own `current_results_dir`** (for example `data/extraction/20261015_111836`) when you want a separate dataset rather than a continuation of the previous one.

#### Run

From the root of the project:

```bash
uv run main.py
```

Progress is printed to the terminal and written to a log file inside `current_results_dir`, named after the moment the run started — `extraction_20261018_114459.log` (a rotating 5 MB log, two backups kept). Each execution gets its own file, so previous runs' logs are never overwritten.

### Output

```
data/
├── videos.jsonl                      # one video per line
├── videos_checkpoint.json            # ["query already done", ...]
├── comments.jsonl                    # one comment per line
├── comments_checkpoint.json          # ["video_id already done", ...]
└── extraction_20261018_114459.log    # one log per execution
```

#### `videos.jsonl`

| Field | Description |
| --- | --- |
| `video_id` | YouTube video ID. |
| `video_title` | Original title. |
| `video_description` | Full description, as returned by the API. |
| `published_at` | Publication timestamp (RFC 3339). |
| `channel_title` | Channel display name. |
| `channel_id` | Channel ID, used to drop the channel's own comments later. |
| `video_duration` | ISO 8601 duration, e.g. `PT5M1S`. |
| `clean_title` | Preprocessed title (`null` if nothing survived cleaning). |
| `clean_description` | Preprocessed description (`null` if empty or nothing survived cleaning). |

#### `comments.jsonl`

| Field | Description |
| --- | --- |
| `video_id` | Video the comment belongs to. |
| `comment_id` | YouTube comment ID. |
| `raw_text` | Original comment text. |
| `comment_likes` | Like count at collection time. |
| `comment_replies` | Number of replies (the replies themselves are not collected). |
| `clean_text` | Preprocessed text. |

#### What gets filtered out

- Videos already present in `videos.jsonl`, so repeated terms across queries never duplicate a row.
- Videos under 3 minutes or tagged `#short`, when `remove_short_videos` is `True`.
- Comments written by the video's own channel.
- Comments that are empty after cleaning.
- Replies — only top-level comments are collected, capped at `max_comments_per_video`.

Videos with comments disabled, or otherwise unreachable, are logged and skipped; the run continues.

#### Text cleaning

The `clean_*` fields first have HTML entities decoded (`&amp;` → `&`, `&#39;` → `'`), then emojis, HTML tags, URLs, timestamps (`12:34`), and arrow characters removed, overly repeated letters and punctuation squashed (`loooool` → `lool`), and whitespace collapsed.

The original text is always kept alongside and is never modified — `video_title` and `raw_text` stay exactly as the API returned them, escaped entities included. Search results arrive HTML-escaped, so expect `&#39;` in `video_title` even though `clean_title` reads `'`. That means you can always re-clean from the stored raw text without collecting again.

### Resuming and starting over

Output files are appended to, and checkpoints are written after each query (videos) and after each video (comments), so an interrupted run is safe to repeat.

- **Add a new query** — append it to `queries` and run again. Queries listed in `videos_checkpoint.json` are skipped, so only the new one costs quota.
- **Start a clean dataset** — point `current_results_dir` at a new directory, or delete the four files in the current one.
- **Careful when deleting only a checkpoint** — removing `videos_checkpoint.json` re-runs the searches but the duplicate check still protects `videos.jsonl`. Removing `comments_checkpoint.json` has no such protection: every comment is fetched and appended a second time.

The whole `data/` directory is gitignored, so collected datasets never enter the repository. Back them up deliberately — nothing in git protects them.

### API quota

The YouTube Data API gives a project 10,000 units per day by default:

| Call | Cost | Made once per |
| --- | --- | --- |
| `search.list` | 100 units | page of up to 50 videos |
| `videos.list` | 1 unit | batch of up to 50 videos (durations and full descriptions) |
| `commentThreads.list` | 1 unit | page of up to 100 comments |

The video stage is the expensive one: `results_per_search: 200` with a single query costs about 404 units, while collecting 100,000 comments costs around 1,000. When quota runs out the API returns `403 quotaExceeded` — the checkpoints let you pick the run back up the next day.

### Project structure

```
main.py                              # entry point: videos stage, then comments stage
src/
├── config.py                        # all user-facing settings
├── extraction/
│   ├── extraction_pipeline.py       # orchestration, checkpointing, deduplication
│   ├── yt_videos_retrieval.py       # search.list + videos.list, Shorts filter
│   └── yt_comments_retrieval.py     # commentThreads.list, comment filter
└── utils/
    ├── api.py                       # shared API client, quota-aware request execution
    ├── handle_config.py             # applies defaults, validates the API key, builds paths
    ├── helpers.py                   # JSONL streaming and text preprocessing
    └── logger.py                    # console + rotating file logger
tests/
├── fakes.py                         # fake YouTube client, HttpError builder
├── conftest.py                      # fixtures: fake-client install, logger cleanup
└── test_*.py                        # one file per module, plus test_isolation.py
```
