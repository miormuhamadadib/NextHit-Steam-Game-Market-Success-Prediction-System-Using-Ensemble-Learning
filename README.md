# ✦ NextHit: Predictive Market Intelligence for Steam Games

[![Project Status](https://img.shields.io/badge/Status-In_Progress-yellow)]()

## 🚀 Project Overview
**NextHit** is an AI-driven predictive market intelligence platform engineered for indie game developers. By transforming pre-launch metadata into actionable insights, this system empowers developers to forecast the commercial success of their titles before they ever hit the market. 🎮

*Note: This project is currently in active development and refinement as part of a Final Year Project.*

## 🧠 Technical Methodology
Our prediction engine is built on robust data science principles to ensure accuracy and fairness:
*   **Ensemble Learning**: We utilize an optimized **XGBoost** model to classify Steam games into success tiers. 📈
*   **Addressing Data Imbalance**: To ensure the model performs reliably across all success categories, we implement the **SMOTETomek** hybrid technique to balance the training dataset. ⚖️
*   **Predictive Analytics**: The engine analyzes key pre-launch metadata—including pricing, language support, and platform breadth—to predict potential market outcomes. 🔮

## ✨ Key Features
*   **AI Engine**: Accurate market success forecasting. 🤖
*   **Smart Advisor**: Provides context-aware recommendations based on identified market influencers. 💡
*   **Dashboard**: A secure, premium dark-mode interface for tracking predictions and managing game portfolios. 📊
*   **Secure Infrastructure**: Features Role-Based Access Control (RBAC) and end-to-end data security. 🔒

## 🛠️ Tech Stack
*   **Backend**: Python (Flask) 🐍
*   **ML Pipeline**: Scikit-learn, XGBoost, imbalanced-learn (SMOTETomek), Joblib ⚙️
*   **Database**: MySQL 🗄️
*   **Security**: Werkzeug, SendGrid API 📧
*   **Data Management**: Git LFS 💾

## ⚙️ Quick Start Guide

Follow these steps to set up the development environment.

### 1. Prerequisites
Ensure **Python**, **MySQL**, and **Git LFS** are installed on your machine.

### 2. Setup
1.  **Clone the repository**:
    ```bash
    git clone [https://github.com/miormuhamadadib/NextHit-Steam-Game-Market-Success-Prediction-System-Using-Ensemble-Learning.git](https://github.com/miormuhamadadib/NextHit-Steam-Game-Market-Success-Prediction-System-Using-Ensemble-Learning.git)
    cd NextHit-Steam-Game-Market-Success-Prediction-System-Using-Ensemble-Learning
    ```
2.  **Sync Large Files**:
    ```bash
    git lfs pull
    ```
3.  **Environment Setup**:
    ```bash
    python -m venv venv
    .\venv\Scripts\activate
    pip install -r requirements.txt
    ```

### 3. Configuration & Launch
1.  **Configure Environment**: Create a `.env` file in the root directory:
    ```text
    DB_PASSWORD=your_mysql_password
    SENDGRID_API_KEY=your_sendgrid_key
    SENDGRID_FROM_EMAIL=your_email@example.com
    SECRET_KEY=your_flask_secret_key
    ```
2.  **Initialize Database**: Ensure your MySQL server is running and import the project schema.
3.  **Run Application**:
    ```bash
    python app.py
    ```

## 🎓 Academic Context
This research is being conducted as a Final Year Project at **Universiti Teknologi MARA (UiTM)**, focusing on reducing financial uncertainty in the indie gaming landscape. 🎓

---
**Authors:**
*   Mior Muhamad Adib Bin Mior Sulman 👨‍💻
