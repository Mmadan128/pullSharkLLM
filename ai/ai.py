import os
import json
import requests
import sqlite3
import pandas as pd
from typing import TypedDict, List, Dict, Any, Optional
from datetime import datetime, timezone
from dotenv import load_dotenv

# AI & Data Imports
import google.generativeai as genai

# Try importing Pathway (Linux/WSL required)
try:
    import pathway as pw
    HAS_PATHWAY = True
except ImportError:
    print("⚠️ Pathway not installed. Using Python list processing fallback.")
    HAS_PATHWAY = False

# Try importing Supabase
try:
    from supabase import create_client, Client
    HAS_SUPABASE = True
except ImportError:
    HAS_SUPABASE = False

# Load environment variables
load_dotenv()

# ============================================================================
# CONFIGURATION
# ============================================================================

GITHUB_API_BASE = "https://api.github.com"
GITHUB_TOKEN = os.getenv('GITHUB_TOKEN')
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')

# Supabase config
SUPABASE_URL = os.getenv('SUPABASE_URL')
SUPABASE_KEY = os.getenv('SUPABASE_KEY')

# SQLite fallback
SQLITE_DB = 'pullshark.db'

# Test mode flag
TEST_MODE = os.getenv('TEST_MODE', 'false').lower() == 'true'

# Determine Database
USE_SUPABASE = HAS_SUPABASE and SUPABASE_URL and SUPABASE_KEY
DB_TYPE = 'supabase' if USE_SUPABASE else 'sqlite'

# ============================================================================
# PATHWAY SCHEMA & MOCK DATA
# ============================================================================

if HAS_PATHWAY:
    class BugSchema(pw.Schema):
        """Pathway schema for bug records"""
        issue_id: str
        issue_title: str
        issue_description: str
        repo: str
        pattern: str
        solution: str

SAMPLE_BUGS = [
    {
        'issue_id': 'BUG-001',
        'issue_title': 'Payment processing race condition',
        'issue_description': 'Concurrent payment transactions causing duplicate charges during high load.',
        'repo': 'myorg/payment-service',
        'pattern': 'race_condition',
        'solution': 'Add transaction locks and idempotency keys'
    },
    {
        'issue_id': 'BUG-002',
        'issue_title': 'Auth token expiration bug',
        'issue_description': 'JWT token refresh logic fails on concurrent requests causing 401 errors.',
        'repo': 'myorg/auth-service',
        'pattern': 'token_management',
        'solution': 'Implement proper token TTL and grace period'
    },
    {
        'issue_id': 'BUG-003',
        'issue_title': 'SQL Injection in Search',
        'issue_description': 'Search endpoint does not sanitize inputs allowing SQL injection.',
        'repo': 'myorg/api-gateway',
        'pattern': 'security_bypass',
        'solution': 'Use parameterized queries'
    }
]

def semantic_search_bugs(query_text: str, k: int = 3) -> List[Dict]:
    """
    Simulates a semantic search. 
    In a production Pathway app, this would use pw.io.http to query a running vector index.
    """
    print(f"🔍 Searching knowledge base for: '{query_text[:50]}...'")
    
    keywords = set(query_text.lower().split())
    results = []
    
    # Simple relevance scoring for demo purposes
    for bug in SAMPLE_BUGS:
        score = 0
        text = (bug['issue_title'] + " " + bug['issue_description']).lower()
        
        for word in keywords:
            if len(word) > 4 and word in text:
                score += 1
        
        if score > 0:
            bug_copy = bug.copy()
            bug_copy['score'] = score
            results.append(bug_copy)
            
    results = sorted(results, key=lambda x: x['score'], reverse=True)[:k]
    return results

# ============================================================================
# DATABASE LAYER
# ============================================================================

class Database:
    def __init__(self):
        if USE_SUPABASE:
            self.client: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
            print("✅ DB: Connected to Supabase")
        else:
            self._init_sqlite()
            print("✅ DB: Using Local SQLite")
    
    def _init_sqlite(self):
        conn = sqlite3.connect(SQLITE_DB)
        c = conn.cursor()
        
        # Create tables
        c.execute('''CREATE TABLE IF NOT EXISTS historical_prs 
                     (id INTEGER PRIMARY KEY, repo TEXT, title TEXT, status TEXT, bugs_found INTEGER, created_at TIMESTAMP)''')
        c.execute('''CREATE TABLE IF NOT EXISTS documentation 
                     (id INTEGER PRIMARY KEY, repo TEXT, module TEXT, content TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS pr_analyses 
                     (id INTEGER PRIMARY KEY, pr_number INTEGER, repo TEXT, author TEXT, 
                      test_plan TEXT, status TEXT, risk_score INTEGER, bugs_found INTEGER, created_at TIMESTAMP)''')
        conn.commit()
        conn.close()
    
    def get_historical_data(self, repo: str) -> List[Dict]:
        # Returns mock historical data for the demo
        return [
            {'title': 'Fix payment retry logic', 'outcome': 'merged', 'bugs_found': 2},
            {'title': 'Update dependencies', 'outcome': 'merged', 'bugs_found': 0}
        ]

    def log_analysis(self, record: Dict) -> bool:
        if USE_SUPABASE:
            try:
                self.client.table('pr_analyses').insert(record).execute()
                return True
            except Exception as e:
                print(f"❌ Supabase Error: {e}")
                return False
        else:
            try:
                conn = sqlite3.connect(SQLITE_DB)
                c = conn.cursor()
                c.execute('''INSERT INTO pr_analyses (pr_number, repo, author, test_plan, status, risk_score, bugs_found, created_at)
                             VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
                          (record['pr_number'], record['repo'], record['author'], json.dumps(record['test_plan']),
                           record['status'], record['risk_score'], record['pathway_bugs_found'], record['timestamp']))
                conn.commit()
                conn.close()
                return True
            except Exception as e:
                print(f"❌ SQLite Error: {e}")
                return False

db = Database()

# ============================================================================
# STATE MANAGEMENT
# ============================================================================

class PullSharkState(TypedDict):
    pr_number: int
    pr_title: str
    pr_description: str
    author: str
    repo: str
    diff_content: str
    risk_score: int
    timestamp: str
    similar_bugs: List[Dict]
    historical_prs: List[Dict]
    test_plan: Dict
    formatted_comment: str
    status: str

# ============================================================================
# WORKFLOW NODES
# ============================================================================

def get_github_headers():
    return {
        'Authorization': f'token {GITHUB_TOKEN}',
        'Accept': 'application/vnd.github.v3+json'
    }

def extract_pr_data(repo: str, pr_number: int) -> PullSharkState:
    print(f"\n📥 [1/5] Fetching PR Data for {repo}#{pr_number}...")
    
    # Demo Mode Fallback
    if TEST_MODE or not GITHUB_TOKEN:
        print("   ⚠️ Test Mode or No Token: Using Mock Data")
        return {
            'pr_number': pr_number,
            'pr_title': 'Feat: Add Stripe Payment Processing',
            'pr_description': 'Implements stripe charge logic and token validation.',
            'author': 'dev_user',
            'repo': repo,
            'diff_content': '+ stripe.Charge.create(amount=100)\n+ if not token: raise Error',
            'risk_score': 8,
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'similar_bugs': [], 'historical_prs': [], 'test_plan': {}, 'formatted_comment': '', 'status': 'pending'
        }

    try:
        # Fetch PR
        pr_url = f"{GITHUB_API_BASE}/repos/{repo}/pulls/{pr_number}"
        pr_res = requests.get(pr_url, headers=get_github_headers())
        pr_res.raise_for_status()
        pr_data = pr_res.json()

        # Fetch Diff
        diff_url = f"{GITHUB_API_BASE}/repos/{repo}/pulls/{pr_number}.diff"
        diff_res = requests.get(diff_url, headers=get_github_headers())
        diff_content = diff_res.text

        # Simple Risk Calc
        keywords = ['auth', 'payment', 'security', 'db', 'delete']
        risk = sum(2 for kw in keywords if kw in pr_data['title'].lower() or kw in diff_content.lower())

        return {
            'pr_number': pr_data['number'],
            'pr_title': pr_data['title'],
            'pr_description': pr_data['body'] or '',
            'author': pr_data['user']['login'],
            'repo': repo,
            'diff_content': diff_content[:2000], # Truncate for context window
            'risk_score': min(risk, 10),
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'similar_bugs': [], 'historical_prs': [], 'test_plan': {}, 'formatted_comment': '', 'status': 'pending'
        }
    except Exception as e:
        print(f"❌ Error fetching GitHub data: {e}")
        raise

def augment_context(state: PullSharkState) -> PullSharkState:
    print(f"\n🧠 [2/5] Retrieving Context (RAG)...")
    
    # 1. Search Pathway/Knowledge Base
    query = f"{state['pr_title']} {state['diff_content'][:200]}"
    state['similar_bugs'] = semantic_search_bugs(query)
    
    # 2. Get Historical Stats
    state['historical_prs'] = db.get_historical_data(state['repo'])
    
    print(f"   ✅ Found {len(state['similar_bugs'])} relevant past bugs")
    return state

def generate_test_plan(state: PullSharkState) -> PullSharkState:
    print(f"\n🤖 [3/5] Generating Test Plan with Gemini...")
    
    if not GEMINI_API_KEY:
        print("   ⚠️ No Gemini Key. Skipping LLM.")
        state['test_plan'] = {'error': 'No API Key'}
        return state

    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel('gemini-2.5-flash')
    
    prompt = f"""
    Act as a Senior QA Engineer. Create a JSON test plan for this Pull Request.
    
    PR Title: {state['pr_title']}
    Risk Score: {state['risk_score']}/10
    Diff Summary: {state['diff_content'][:500]}...
    
    Known Bugs in similar code:
    {json.dumps(state['similar_bugs'], indent=2)}
    
    Return ONLY valid JSON with these keys:
    - edge_cases (list of strings)
    - security_risks (list of strings)
    - recommended_tests (list of strings)
    - priority (High/Medium/Low)
    """
    
    try:
        response = model.generate_content(prompt, generation_config={'response_mime_type': 'application/json'})
        state['test_plan'] = json.loads(response.text)
        state['status'] = 'success'
    except Exception as e:
        print(f"❌ Gemini Error: {e}")
        state['test_plan'] = {"error": "Generation failed"}
        state['status'] = 'failed'
        
    return state

def post_comment(state: PullSharkState) -> PullSharkState:
    print(f"\n📝 [4/5] Formatting & Posting Comment...")
    
    plan = state.get('test_plan', {})
    if 'error' in plan:
        print("   ⚠️ Skipping comment due to generation error.")
        return state
        
    priority_emoji = "🔴" if plan.get('priority') == 'High' else "🟡"
    
    comment = f"""## 🦈 PullShark AI Analysis
    
**Risk Level**: {priority_emoji} {plan.get('priority', 'Unknown')}

### 🧪 Recommended Tests
{chr(10).join(f"- [ ] {t}" for t in plan.get('recommended_tests', []))}

### ⚠️ Edge Cases & Security
{chr(10).join(f"- {t}" for t in plan.get('edge_cases', []) + plan.get('security_risks', []))}

---
*Generated by PullShark using Gemini & Pathway*
    """
    state['formatted_comment'] = comment
    
    if not TEST_MODE and GITHUB_TOKEN:
        try:
            url = f"{GITHUB_API_BASE}/repos/{state['repo']}/issues/{state['pr_number']}/comments"
            res = requests.post(url, json={'body': comment}, headers=get_github_headers())
            res.raise_for_status()
            print("   ✅ Comment posted to GitHub")
        except Exception as e:
            print(f"   ❌ Failed to post comment: {e}")
    else:
        print("   ℹ️ (Dry Run) Comment not posted.")
        
    return state

def save_results(state: PullSharkState):
    print(f"\n💾 [5/5] Saving to Database...")
    
    record = {
        'pr_number': state['pr_number'],
        'repo': state['repo'],
        'author': state['author'],
        'test_plan': state['test_plan'],
        'status': state['status'],
        'risk_score': state['risk_score'],
        'pathway_bugs_found': len(state['similar_bugs']),
        'timestamp': state['timestamp']
    }
    
    db.log_analysis(record)
    print("✅ Workflow Complete!")

# ============================================================================
# MAIN ENTRY POINT
# ============================================================================

if __name__ == "__main__":
    import sys
    
    # Default usage or CLI arguments
    target_repo = sys.argv[1] if len(sys.argv) > 1 else "octocat/Hello-World"
    target_pr = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    
    print(f"🦈 Starting PullShark on {target_repo} PR #{target_pr}")
    
    try:
        # Run Workflow
        state = extract_pr_data(target_repo, target_pr)
        state = augment_context(state)
        state = generate_test_plan(state)
        state = post_comment(state)
        save_results(state)
        
        print("\n--- Final Output ---")
        print(state['formatted_comment'])
        
    except KeyboardInterrupt:
        print("\n🛑 Operation cancelled.")
    except Exception as e:
        print(f"\n❌ Critical Failure: {e}")