# ✒️ Fonts Portfolio — Da Ilustração à Tipografia

<p align="center">
  <img src="https://img.shields.io/badge/Status-Em%20Cria%C3%A7%C3%A3o-orange?style=for-the-badge&logo=font-awesome" alt="Status">
  <img src="https://img.shields.io/badge/Formatos-OTF%20%7C%20TTF%20%7C%20WOFF2-blue?style=for-the-badge" alt="Formatos">
  <img src="https://img.shields.io/badge/Licen%C3%A7a-OFL%201.1%20%2F%20Autoral-brightgreen?style=for-the-badge" alt="Licença">
</p>

<p align="center">
  <i>Um laboratório tipográfico autoral focado em transformar traços, ilustrações manuais e experimentações gráficas em fontes digitais completas e funcionais.</i>
</p>

---

## 🎨 Sobre o Projeto

Este repositório foi criado para ser o **acervo e atelier digital** de criação de fontes tipográficas.

Cada fonte aqui nasce fora do computador: no caderno de rascunhos, nas folhas soltas, na caneta nanquim, no lápis, no pincel ou na pintura digital. O objetivo deste projeto é preservar a alma, o gesto e a organicidade do desenho manual enquanto desenvolvemos a precisão técnica necessária para que o resultado funcione impecavelmente em softwares gráficos, sistemas operacionais e na web.

> *"A tipografia é a voz do texto — e desenhar letras é dar corpo e sotaque a essa voz."*

---

## 🧭 Do Esboço ao Glifo (Pipeline de Criação)

O processo criativo e técnico segue um ciclo artesanal e estruturado:

```mermaid
flowchart LR
    A["✏️ 1. Desenho & Conceito\nRascunhos manuais, caligrafia e estudo de formas"] --> B["📐 2. Vetorização\nDigitalização e ajuste fino de curvas Bézier"]
    B --> C["🔤 3. Engenharia de Glifos\nMétricas, kerning, acentuação e OpenType"]
    C --> D["📦 4. Compilação & Export\nGeração dos formatos OTF, TTF e WOFF2"]
    D --> E["📜 5. Espécime & Teste\nValidação visual em textos, títulos e layouts"]
```

1. **Desenho & Pesquisa:** Estudos de ritmo, contraste, espessuras e proporções em papel ou mesa digitalizadora.
2. **Vetorização Precisa:** Limpeza de ruído e construção de caminhos limpos com o menor número possível de âncoras.
3. **Métricas & Espaçamento:** Ajuste individual de avanço (advance width), pares de kerning e conjunto de caracteres (A-Z, numerais, pontuação e diacríticos para o português e outros idiomas).
4. **Exportação & Otimização:** Conversão para formatos OpenType (`.otf`), TrueType (`.ttf`) e fontes para a web (`.woff` / `.woff2`).
5. **Amostra Tipográfica (Specimen):** Criação de pôsteres e amostras demonstrando o comportamento em diferentes corpos de texto.

---

## 🗂️ Estrutura do Repositório

O repositório é organizado para separar o produto final pronto para uso das etapas de processo:

```text
fonts/
│
├── fonts/               # 📦 Arquivos compilados das fontes prontos para instalar e usar
│   ├── otf/             # OpenType Font (ideal para desktop e softwares de design)
│   ├── ttf/             # TrueType Font (compatibilidade universal)
│   └── web/             # WOFF / WOFF2 (otimizado para websites e apps)
│
├── sources/             # 🎨 Arquivos de origem e processo criativo
│   ├── drawings/        # Scans, fotos dos sketches e rascunhos originais
│   └── vectors/         # Arquivos vetoriais brutos (SVG, EPS, Illustrator, etc.)
│
├── specimens/           # 🖼️ Amostras visuais, testes de texto e cartazes de apresentação
├── docs/                # 📝 Notas sobre características de cada família e histórico de versões
├── .gitignore           # Ignora temporários e caches de editores tipográficos
└── README.md            # Documentação principal do repositório
```

---

## 📚 Catálogo de Fontes

| Fonte | Estilo / Vibe | Conjunto Suportado | Formatos | Status |
| :--- | :--- | :--- | :---: | :---: |
| **[AnoDragonDisplay](fonts/otf/AnoDragonDisplay-Regular.otf)** | *Display Orgânica / Bubble Ultra-Bold* | A-Z, a-z, Acentuação PT, Números, Símbolos, 14 Setas, Emojis, Lírio e Dragão | `.otf`, `.ttf`, `.woff2` | 🟢 **Concluída (v1.0)** |
| **[AnoDragonDisplay-Core](fonts/otf/AnoDragonDisplay-Core.otf)** | *Núcleo Interno (Camada Cromática)* | Cobertura Unicode idêntica para sobreposição 3D com a base | `.otf`, `.ttf`, `.woff2` | 🟢 **Concluída (v1.0)** |

---

### 🐉 Destaque: A Família *AnoDragonDisplay*

Nascida da vetorização por visão computacional e engenharia reversa do lettering **"ANO"** presente na ilustração original do dragão oriental:

- **DNA Tipográfico:** Silhueta inflada *ultra-bold*, terminais orgânicos e a marcante assinatura dos **contragrafismos em micro-círculos (*pinpoint counters*)** no terço superior de todas as letras fechadas (`A`, `B`, `D`, `O`, `P`, `Q`, `R`, `a`, `b`, `d`, `e`, `g`, `o`, `p`, `q`, `0`, `4`, `6`, `8`, `9`, `@`).
- **Sistema Cromático em Camadas:** Use a variante `Regular` (silhueta/contorno creme `#DCE29F`) combinada com a variante `Core` (núcleo verde-oliva `#262D13`) para obter exatamente o acabamento tridimensional da arte original!
- **Easter Eggs Temáticos:** Inclui os glifos especiais de **Flor de Lírio** (`✿` `U+273F`) e **Dragão Oriental** (`🐉` `U+1F409`).
- **Espécime Visual Interativo:** Abra [specimens/specimen.html](specimens/specimen.html) no navegador para testar digitação ao vivo, comparar com a arte original e explorar o mapa de caracteres.

---

## 🚀 Como Instalar e Utilizar

### No Computador (Desktop)
1. Acesse a pasta `fonts/otf` ou `fonts/ttf`.
2. Baixe o arquivo desejado (ex: [AnoDragonDisplay-Regular.otf](fonts/otf/AnoDragonDisplay-Regular.otf)).
3. Dê dois cliques no arquivo baixado e clique em **Instalar Fonte** (Windows / macOS / Linux).
4. A fonte estará disponível no Photoshop, Illustrator, Figma, Canva, Word, etc.

### Na Web (@font-face)
Copie o arquivo `.woff2` da pasta `fonts/web/` para seu projeto e declare no seu CSS:

```css
@font-face {
  font-family: 'AnoDragonDisplay';
  src: url('./fonts/web/AnoDragonDisplay-Regular.woff2') format('woff2');
  font-weight: 900;
  font-style: normal;
  font-display: swap;
}

@font-face {
  font-family: 'AnoDragonDisplay-Core';
  src: url('./fonts/web/AnoDragonDisplay-Core.woff2') format('woff2');
  font-weight: 900;
  font-style: normal;
  font-display: swap;
}

/* Efeito cromático idêntico à arte original */
.dragao-lettering {
  font-family: 'AnoDragonDisplay', sans-serif;
  color: #dce29f; /* contorno creme */
  position: relative;
}
.dragao-lettering::after {
  content: attr(data-text);
  font-family: 'AnoDragonDisplay-Core', sans-serif;
  color: #222912; /* núcleo verde-oliva */
  position: absolute;
  left: 0;
  top: 0;
}
```

---

## 🛠️ Ferramentas Utilizadas

- **Papel, canetas e tintas:** Nanquim, brush pen, marcadores e grafite
- **Digitalização:** Scanner de alta resolução & Procreate / Photoshop
- **Vetorização:** Adobe Illustrator / Inkscape
- **Criação & Edição Tipográfica:** Glyphs / FontForge / BirdFont / RoboFont / Fontself
- **Otimização Web:** Fonttools & WOFF2 compressors

---

## ⚖️ Licença

As fontes e materiais gráficos deste repositório são protegidos por direitos autorais. Consulte o arquivo [LICENSE](LICENSE) para termos específicos de uso pessoal, comercial ou sob licença aberta (SIL Open Font License).

---

<p align="center">
  Feito com amor, café e muita ponta de caneta ✒️✨
</p>

