# ✦ NextHit: Predictive Market Intelligence for Steam Games

[![Project Status](https://img.shields.io/badge/Status-Completed-success)]()

## 🚀 Project Overview
**NextHit** is an AI-driven predictive market intelligence platform engineered for indie game developers. By transforming pre-launch metadata into actionable insights, this system empowers developers to forecast the commercial success of their titles before they ever hit the market. 🎮

## 🧠 Technical Methodology
Our prediction engine is built on robust data science principles to ensure accuracy and fairness:
*   **Ensemble Learning**: We utilize an optimized **XGBoost** model to classify Steam games into success tiers. 📈
*   **Addressing Data Imbalance**: To ensure the model performs reliably across all success categories, we implement the **SMOTETomek** hybrid technique to balance the training dataset. ⚖️
*   **Predictive Analytics**: The engine analyzes key metadata—including pricing, language support, and platform breadth—to predict potential market outcomes. 🔮

## ✨ Key Features
*   **AI Engine**: Accurate market success forecasting. 🤖
*   **Smart Advisor**: Receives context-aware recommendations based on identified market influencers. 💡
*   **Dashboard**: A secure, premium dark-mode interface for tracking predictions and managing game portfolios. 📊
*   **Secure Infrastructure**: Features Role-Based Access Control (RBAC) and end-to-end data security. 🔒

## 🛠️ Tech Stack
*   **Backend**: Python (Flask) 🐍
*   **ML Pipeline**: Scikit-learn, XGBoost, imbalanced-learn (SMOTETomek), Joblib ⚙️
*   **Database**: MySQL 🗄️
*   **Security**: Werkzeug, SendGrid API 📧
*   **Data Management**: Git LFS 💾

## ⚙️ Setup and Installation

### 1. Prerequisites
Ensure Python and MySQL are installed. You will need **Git LFS** installed to sync our large AI model artifacts.

### 2. Environment Configuration
Create a `.env` file in the project root:
```text
DB_PASSWORD=your_mysql_password
SENDGRID_API_KEY=your_sendgrid_key
SENDGRID_FROM_EMAIL=your_email@example.com
SECRET_KEY=your_flask_secret_key
