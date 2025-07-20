# Neuro-Crypto Content Factory 🤖

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

A fully autonomous content pipeline that plans, generates, and delivers personalized crypto news digests. This system operates 24/7, transforming raw data from various sources into high-quality, multi-modal content tailored to user preferences.

## ✨ Key Features

-   **Autonomous Operation**: Runs on a schedule, requiring zero daily intervention.
-   **Strategic & Tactical Planning**: Employs a two-tier planning system (weekly strategy, daily tactics) to guide content creation.
-   **Multi-Source Data Collection**: Gathers news from Telegram channels and the Bybit Learn portal.
-   **Cascading AI Processing**: Uses a sophisticated pipeline of AI models (Gemini, Grok) to summarize, categorize, rebalance, and enrich raw news.
-   **Multi-Modal Content Generation**: Creates not just text articles but also unique cover images for each piece.
-   **Personalization via "Personas"**: Users can subscribe to different content styles, from academic analysis to provocative insider takes.
-   **Robust GUI Automation**: Manages external desktop applications (like ProtonVPN) by visually locating and clicking buttons, ensuring reliability where CLI fails.
-   **Automated Delivery**: Packages content into `.zip` archives and delivers them directly to users via a Telegram Bot.
-   **Resilience & Monitoring**: Built-in VPN management and an alerting system for critical failures.

## 🛠️ Tech Stack & Architecture

-   **Core**: Python 3.10+
-   **Scheduling**: `APScheduler`
-   **AI & ML**: `google-generativeai`, `openai` (for Grok), `huggingface-hub`, `scikit-learn`, `numpy`
-   **Data Collection**: `Telethon`, `requests`
-   **Database**: `sqlite3`
-   **GUI Automation**: `PyAutoGUI`, `opencv-python`
-   **Telegram Bot**: `python-telegram-bot`
-   **File Handling**: `python-docx`, `zipfile`, `Pillow`

## ⚙️ How It Works

The system operates in two main cycles: a weekly strategic cycle and a daily execution pipeline.

### Weekly Strategy Cycle (Mondays)
1.  **`strategic_planner`** runs, using an AI prompt to generate a high-level content plan for the upcoming week.
2.  This plan defines the target ratio of different topic categories and distributes the content creation tasks for each "Persona" across the days of the week.
3.  The plan is saved to the `weekly_plan` table in the database.

### Daily Execution Pipeline
The `daily_pipeline` is triggered by the `scheduler` every morning.

1.  **Preparation & Data Collection**:
    -   `vpn_manager` establishes a secure VPN connection using **GUI automation** to interact with the ProtonVPN desktop client.
    -   `tokens` and `bybit_parser` fetch the latest token lists and articles from Bybit.
    -   `telegram_channel_scraper` gathers news from specified Telegram channels.

2.  **Processing & Enrichment**:
    -   `news_summarizer` creates a master summary of unique news events for the day.
    -   `topic_categorizer` assigns a technical category to each news item using embeddings and **`cosine_similarity`**.
    -   `topic_rebalancer` adjusts these categories to align with the weekly strategic plan.
    -   `title_formatter` generates a compelling headline for each topic.

3.  **Tactical Planning & Content Generation**:
    -   `daily_planner` assigns the prepared topics to users based on their subscriptions and the daily plan.
    -   The asynchronous content factory kicks in:
        -   `article_writter` generates full-text articles using the appropriate AI model (Gemini/Grok).
        -   `picture_generator` creates a unique cover image for each article.
        -   `token_matcher` analyzes the article text to identify relevant crypto tickers.

4.  **Packaging & Delivery**:
    -   `doc_zipper` compiles the article text, image, and metadata into a `.docx` file and packages everything into a user-specific `.zip` archive.
    -   `telegram_bot` sends the generated `.zip` digest to each subscribed user.
    -   `vpn_manager` disconnects the VPN, completing the cycle.

## 🚀 Getting Started

### Prerequisites
-   Python 3.10 or higher
-   **ProtonVPN Desktop Client** installed and configured.
-   API keys for Google Gemini, Grok, and Hugging Face.
-   Telegram API credentials (`api_id`, `api_hash`) and a Bot Token.

### Installation
1.  **Clone the repository:**
    ```bash
    git clone https://github.com/Apartman36/NEURO-CRYPTO.git
    cd NEURO-CRYPTO
    ```

2.  **Create a virtual environment and activate it:**
    ```bash
    python -m venv venv
    source venv/bin/activate  # On Windows, use `venv\Scripts\activate`
    ```

3.  **Install the dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

4.  **Configure the environment:**
    -   Create a `.env` file (you can copy `.env.example` if you have one) and fill in your API keys, Telegram IDs, and other credentials.
    -   Review and adjust the settings in the various `_config.json` files.
    -   Place `connect_button.png` and `disconnect_button.png` in the root directory. These are screenshots of your ProtonVPN client's buttons.

5.  **Initialize the database:**
    This will create the `neuro_crypto.db` file and all necessary tables.
    ```bash
    python database_manager.py
    ```

6.  **Seed the database with initial data:**
    This populates the `personas` table.
    ```bash
    python seed.py
    ```

7.  **Create a Telegram session file:**
    Run this script and follow the interactive prompts to log in to your Telegram account. This will create a `my_minimal_session.session` file needed for the scraper.
    ```bash
    python setup_telegram_session.py
    ```

## ▶️ Usage

-   **To run the daily pipeline once for testing:**
    ```bash
    python daily_pipeline.py
    ```

-   **To start the scheduler for continuous, automated operation:**
    ```bash
    python scheduler.py
    ```

## 📂 Project Structure
```
/
├── .venv/                      // Python virtual environment
├── categorized_news/           // Stores JSON files with categorized news
├── daily_summaries/            // Stores raw daily news summaries from scrapers
├── daily_zips/                 // Output directory for final user ZIP digests
├── Gen_Photo/                  // Output directory for generated images
├── master_summaries/           // Stores cleaned, de-duplicated master news summaries
├── Prompts/                    // Contains all .txt prompts for AI models
│   ├── article_writer_prompt.txt
│   └── ...
├── .env                        // Stores all secret keys and credentials
├── .gitignore                  // Specifies intentionally untracked files
├── *_config.json               // Configuration files for various modules
├── *.py                        // The core Python modules of the project
├── connect_button.png          // Image asset for VPN GUI automation
├── disconnect_button.png       // Image asset for VPN GUI automation
├── base_currencies.txt         // List of crypto tokens from Bybit
├── my_minimal_session.session  // Session file for Telethon
├── neuro_crypto.db             // The SQLite database file
└── requirements.txt            // List of all Python dependencies
```

## 📄 License
This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.
