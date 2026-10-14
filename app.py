from flask import Flask, render_template, request, redirect, session, url_for
import os
import sqlite3

app = Flask(__name__)
app.secret_key = "cspm_secret"
DB_PATH = os.path.join(os.path.dirname(__file__), "database.db")


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def calculate_risk(asset_type, environment, public_access, encryption, compliance_status):
    score = 20

    if asset_type == "S3":
        score += 10
    elif asset_type == "Database":
        score += 15
    elif asset_type == "VM":
        score += 8

    if environment == "Production":
        score += 10

    if public_access == "Yes":
        score += 45

    if encryption == "No":
        score += 35

    if compliance_status == "Needs Attention":
        score += 25
    elif compliance_status == "Critical":
        score += 35

    if score >= 80:
        severity = "Critical"
        remediation = "Isolate the workload, enable strict IAM and encryption controls, and remediate the underlying misconfiguration immediately."
    elif score >= 55:
        severity = "High"
        remediation = "Apply least-privilege access, tighten encryption settings, and review the workload for exposed services."
    elif score >= 30:
        severity = "Medium"
        remediation = "Introduce baseline controls and schedule a follow-up compliance review."
    else:
        severity = "Low"
        remediation = "Maintain monitoring and keep the asset aligned with existing security standards."

    return score, severity, remediation


def get_metrics(assets):
    total_assets = len(assets)
    critical_issues = sum(1 for asset in assets if asset["severity"] == "Critical")
    compliant_assets = sum(1 for asset in assets if asset["compliance_status"] == "Compliant")
    average_score = round(sum(asset["risk_score"] for asset in assets) / total_assets, 1) if total_assets else 0

    return {
        "total_assets": total_assets,
        "critical_issues": critical_issues,
        "compliant_assets": compliant_assets,
        "average_score": average_score,
    }


# Create Database
def init_db():
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS assets(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        asset_name TEXT NOT NULL,
        asset_type TEXT NOT NULL,
        environment TEXT NOT NULL DEFAULT 'Production',
        region TEXT NOT NULL DEFAULT 'us-east-1',
        owner TEXT NOT NULL DEFAULT 'Platform Team',
        public_access TEXT NOT NULL,
        encryption TEXT NOT NULL,
        compliance_status TEXT NOT NULL DEFAULT 'Needs Attention',
        risk_score INTEGER NOT NULL DEFAULT 0,
        severity TEXT NOT NULL DEFAULT 'Medium',
        remediation TEXT
    )
    """)
    conn.commit()

    cur.execute("PRAGMA table_info(assets)")
    columns = [row[1] for row in cur.fetchall()]
    migrations = {
        "environment": "ALTER TABLE assets ADD COLUMN environment TEXT NOT NULL DEFAULT 'Production'",
        "region": "ALTER TABLE assets ADD COLUMN region TEXT NOT NULL DEFAULT 'us-east-1'",
        "owner": "ALTER TABLE assets ADD COLUMN owner TEXT NOT NULL DEFAULT 'Platform Team'",
        "compliance_status": "ALTER TABLE assets ADD COLUMN compliance_status TEXT NOT NULL DEFAULT 'Needs Attention'",
        "risk_score": "ALTER TABLE assets ADD COLUMN risk_score INTEGER NOT NULL DEFAULT 0",
        "severity": "ALTER TABLE assets ADD COLUMN severity TEXT NOT NULL DEFAULT 'Medium'",
        "remediation": "ALTER TABLE assets ADD COLUMN remediation TEXT"
    }
    for column, statement in migrations.items():
        if column not in columns:
            cur.execute(statement)
    conn.commit()

    cur.execute("SELECT COUNT(*) FROM assets")
    if cur.fetchone()[0] == 0:
        sample_assets = [
            ("web-api", "EC2", "Production", "us-east-1", "App Team", "Yes", "No", "Critical", 84, "Critical", "Isolate the workload, enforce private networking, and rotate credentials immediately."),
            ("analytics-bucket", "S3", "Production", "eu-west-1", "Data Team", "Yes", "No", "Needs Attention", 72, "High", "Restrict public bucket access and enable server-side encryption."),
            ("payments-db", "Database", "Production", "us-west-2", "Platform Team", "No", "Yes", "Compliant", 24, "Low", "Maintain current controls and monitor for drift."),
        ]
        cur.executemany("""
            INSERT INTO assets (asset_name, asset_type, environment, region, owner, public_access, encryption, compliance_status, risk_score, severity, remediation)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, sample_assets)

    conn.commit()
    conn.close()


init_db()


@app.route('/')
def home():
    return render_template('login.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()

        if username == "srujan" and password == "bcacccs":
            session['user'] = username
            session['cloud_connected'] = False
            session['cloud_provider'] = None
            session['cloud_account'] = None
            return redirect('/dashboard')

        return render_template('login.html', error='Invalid username or password')

    return render_template('login.html', error=None)


@app.route('/dashboard', methods=['GET', 'POST'])
def dashboard():
    if 'user' not in session:
        return redirect('/')

    conn = get_db()
    cur = conn.cursor()

    if request.method == 'POST':
        asset_name = request.form.get('asset_name', '').strip()
        asset_type = request.form.get('asset_type', 'EC2')
        environment = request.form.get('environment', 'Production')
        region = request.form.get('region', 'us-east-1')
        owner = request.form.get('owner', 'Platform Team').strip()
        public_access = request.form.get('public_access', 'No')
        encryption = request.form.get('encryption', 'Yes')
        compliance_status = request.form.get('compliance_status', 'Needs Attention')

        if asset_name:
            risk_score, severity, remediation = calculate_risk(asset_type, environment, public_access, encryption, compliance_status)
            cur.execute("""
            INSERT INTO assets (asset_name, asset_type, environment, region, owner, public_access, encryption, compliance_status, risk_score, severity, remediation)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (asset_name, asset_type, environment, region, owner, public_access, encryption, compliance_status, risk_score, severity, remediation))
            conn.commit()

    cur.execute("SELECT * FROM assets ORDER BY risk_score DESC, id DESC")
    assets = cur.fetchall()
    metrics = get_metrics(assets)
    conn.close()

    cloud_connected = session.get('cloud_connected', False)
    cloud_provider = session.get('cloud_provider')
    cloud_account = session.get('cloud_account')

    return render_template(
        'dashboard.html',
        assets=assets,
        metrics=metrics,
        cloud_connected=cloud_connected,
        cloud_provider=cloud_provider,
        cloud_account=cloud_account,
    )


@app.route('/connect-cloud', methods=['POST'])
def connect_cloud():
    if 'user' not in session:
        return redirect('/')

    provider = request.form.get('provider', 'AWS')
    account_name = request.form.get('account_name', '').strip() or 'Demo Account'

    session['cloud_connected'] = True
    session['cloud_provider'] = provider
    session['cloud_account'] = account_name
    return redirect('/dashboard')


@app.route('/scan')
def scan_assets():
    if 'user' not in session:
        return redirect('/')

    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM assets")
    assets = cur.fetchall()

    for asset in assets:
        risk_score, severity, remediation = calculate_risk(asset['asset_type'], asset['environment'], asset['public_access'], asset['encryption'], asset['compliance_status'])
        cur.execute("UPDATE assets SET risk_score=?, severity=?, remediation=? WHERE id=?", (risk_score, severity, remediation, asset['id']))

    conn.commit()
    conn.close()
    return redirect('/dashboard')


@app.route('/report')
def report():
    if 'user' not in session:
        return redirect('/')

    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM assets ORDER BY risk_score DESC, id DESC")
    assets = cur.fetchall()
    metrics = get_metrics(assets)
    top_priority = assets[0] if assets else None
    conn.close()

    return render_template("report.html", findings=assets, metrics=metrics, top_priority=top_priority)


@app.route('/asset/delete/<int:asset_id>')
def delete_asset(asset_id):
    if 'user' not in session:
        return redirect('/')

    conn = get_db()
    cur = conn.cursor()
    cur.execute("DELETE FROM assets WHERE id=?", (asset_id,))
    conn.commit()
    conn.close()
    return redirect('/report')


@app.route('/asset/edit/<int:asset_id>', methods=['GET', 'POST'])
def edit_asset(asset_id):
    if 'user' not in session:
        return redirect('/')

    conn = get_db()
    cur = conn.cursor()

    if request.method == 'POST':
        asset_name = request.form.get('asset_name', '').strip()
        asset_type = request.form.get('asset_type', 'EC2')
        environment = request.form.get('environment', 'Production')
        region = request.form.get('region', 'us-east-1')
        owner = request.form.get('owner', 'Platform Team').strip()
        public_access = request.form.get('public_access', 'No')
        encryption = request.form.get('encryption', 'Yes')
        compliance_status = request.form.get('compliance_status', 'Needs Attention')

        risk_score, severity, remediation = calculate_risk(asset_type, environment, public_access, encryption, compliance_status)

        cur.execute("""
        UPDATE assets
        SET asset_name=?, asset_type=?, environment=?, region=?, owner=?, public_access=?, encryption=?, compliance_status=?, risk_score=?, severity=?, remediation=?
        WHERE id=?
        """, (asset_name, asset_type, environment, region, owner, public_access, encryption, compliance_status, risk_score, severity, remediation, asset_id))

        conn.commit()
        conn.close()
        return redirect('/report')

    cur.execute("SELECT * FROM assets WHERE id=?", (asset_id,))
    asset = cur.fetchone()
    conn.close()

    if not asset:
        return redirect('/report')

    return render_template('edit_asset.html', asset=asset)


@app.route('/logout')
def logout():
    session.clear()
    return redirect('/')


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0')