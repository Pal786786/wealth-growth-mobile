#====================================================================================================
# START - Testing Protocol - DO NOT EDIT OR REMOVE THIS SECTION
#====================================================================================================

# THIS SECTION CONTAINS CRITICAL TESTING INSTRUCTIONS FOR BOTH AGENTS
# BOTH MAIN_AGENT AND TESTING_AGENT MUST PRESERVE THIS ENTIRE BLOCK

# Communication Protocol:
# If the `testing_agent` is available, main agent should delegate all testing tasks to it.
#
# You have access to a file called `test_result.md`. This file contains the complete testing state
# and history, and is the primary means of communication between main and the testing agent.
#
# Main and testing agents must follow this exact format to maintain testing data. 
# The testing data must be entered in yaml format Below is the data structure:
# 
## user_problem_statement: {problem_statement}
## backend:
##   - task: "Task name"
##     implemented: true
##     working: true  # or false or "NA"
##     file: "file_path.py"
##     stuck_count: 0
##     priority: "high"  # or "medium" or "low"
##     needs_retesting: false
##     status_history:
##         -working: true  # or false or "NA"
##         -agent: "main"  # or "testing" or "user"
##         -comment: "Detailed comment about status"
##
## frontend:
##   - task: "Task name"
##     implemented: true
##     working: true  # or false or "NA"
##     file: "file_path.js"
##     stuck_count: 0
##     priority: "high"  # or "medium" or "low"
##     needs_retesting: false
##     status_history:
##         -working: true  # or false or "NA"
##         -agent: "main"  # or "testing" or "user"
##         -comment: "Detailed comment about status"
##
## metadata:
##   created_by: "main_agent"
##   version: "1.0"
##   test_sequence: 0
##   run_ui: false
##
## test_plan:
##   current_focus:
##     - "Task name 1"
##     - "Task name 2"
##   stuck_tasks:
##     - "Task name with persistent issues"
##   test_all: false
##   test_priority: "high_first"  # or "sequential" or "stuck_first"
##
## agent_communication:
##     -agent: "main"  # or "testing" or "user"
##     -message: "Communication message between agents"

# Protocol Guidelines for Main agent
#
# 1. Update Test Result File Before Testing:
#    - Main agent must always update the `test_result.md` file before calling the testing agent
#    - Add implementation details to the status_history
#    - Set `needs_retesting` to true for tasks that need testing
#    - Update the `test_plan` section to guide testing priorities
#    - Add a message to `agent_communication` explaining what you've done
#
# 2. Incorporate User Feedback:
#    - When a user provides feedback that something is or isn't working, add this information to the relevant task's status_history
#    - Update the working status based on user feedback
#    - If a user reports an issue with a task that was marked as working, increment the stuck_count
#    - Whenever user reports issue in the app, if we have testing agent and task_result.md file so find the appropriate task for that and append in status_history of that task to contain the user concern and problem as well 
#
# 3. Track Stuck Tasks:
#    - Monitor which tasks have high stuck_count values or where you are fixing same issue again and again, analyze that when you read task_result.md
#    - For persistent issues, use websearch tool to find solutions
#    - Pay special attention to tasks in the stuck_tasks list
#    - When you fix an issue with a stuck task, don't reset the stuck_count until the testing agent confirms it's working
#
# 4. Provide Context to Testing Agent:
#    - When calling the testing agent, provide clear instructions about:
#      - Which tasks need testing (reference the test_plan)
#      - Any authentication details or configuration needed
#      - Specific test scenarios to focus on
#      - Any known issues or edge cases to verify
#
# 5. Call the testing agent with specific instructions referring to test_result.md
#
# IMPORTANT: Main agent must ALWAYS update test_result.md BEFORE calling the testing agent, as it relies on this file to understand what to test next.

#====================================================================================================
# END - Testing Protocol - DO NOT EDIT OR REMOVE THIS SECTION
#====================================================================================================



#====================================================================================================
# Testing Data - Main Agent and testing sub agent both should log testing data below this section
#====================================================================================================

user_problem_statement: |
  Add centralized API Management + Demo Mode to the My Funding Bank admin dashboard
  (and surface a demo banner on the mobile app). Admin must be able to add/edit API
  keys for Stripe, Razorpay, SMS, Email, Stock Market, Mutual Fund, Gold, Flight,
  Hotel, Push & KYC; enable/disable each; force-demo; and test connection. When a
  key is missing, the integration auto-falls-back to demo data — no errors shown.

backend:
  - task: "API Settings registry + CRUD endpoints (api_settings.py)"
    implemented: true
    working: true
    file: "/app/backend/api_settings.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
        -working: true
        -agent: "main"
        -comment: "New module with catalog of 11 supported integrations. Endpoints: GET /api/admin/api-settings (list), PUT /api/admin/api-settings/{name} (upsert key/enable/force-demo), POST /api/admin/api-settings/{name}/test (test connection — never raises), GET /api/app/api-status (public status feed for mobile banner). Manual curl tests passed for list/update/disable/clear."
  - task: "Refactor Stripe & Alpha Vantage to use centralized api_settings"
    implemented: true
    working: true
    file: "/app/backend/server.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
        -working: true
        -agent: "main"
        -comment: "Stripe top-up now reads key dynamically from api_settings (fallback to env, then to demo). Stripe errors now degrade to demo top-up instead of HTTP 502. Alpha Vantage stocks read key dynamically and add mode flag. /invest/gold-price respects api_settings + manual override."

frontend:
  - task: "Admin: API Management page + nav + global demo banner"
    implemented: true
    working: true
    file: "/app/admin/src/pages/ApiManagement.tsx, /app/admin/src/pages/Layout.tsx, /app/admin/src/main.tsx"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
        -working: true
        -agent: "main"
        -comment: "New Settings → API Management page with stats cards (Live/Demo/Disabled), grouped table by category, expandable rows with masked key, extra fields, force-demo toggle, Test Connection, Enable/Disable, Save. Global amber banner + header badge shown when any_demo>0. Built with `yarn build`, served at /api/admin-ui/."
  - task: "Mobile: Demo Mode banner on Home"
    implemented: true
    working: true
    file: "/app/frontend/app/(tabs)/index.tsx"
    stuck_count: 0
    priority: "medium"
    needs_retesting: true
    status_history:
        -working: true
        -agent: "main"
        -comment: "Home tab now calls /api/app/api-status alongside dashboard + banners. When any_demo=true, shows yellow Demo Mode card with count badge above the hero. Verified visually in preview."

metadata:
  created_by: "main_agent"
  version: "1.1"
  test_sequence: 2
  run_ui: true

test_plan:
  current_focus:
    - "API Settings registry + CRUD endpoints (api_settings.py)"
    - "Refactor Stripe & Alpha Vantage to use centralized api_settings"
    - "Admin: API Management page + nav + global demo banner"
    - "Mobile: Demo Mode banner on Home"
  stuck_tasks: []
  test_all: false
  test_priority: "high_first"

agent_communication:
    -agent: "main"
    -message: |
      Implemented full API Management + Demo Mode system.
      Backend additions:
        • /app/backend/api_settings.py (new module)
        • Wired into /app/backend/server.py (router + startup seed)
        • Stripe & Alpha Vantage now read key dynamically — graceful demo fallback
        • Public endpoint /api/app/api-status for mobile banner
      Admin UI:
        • New /api-management route with full CRUD + Test Connection
        • Global Demo Mode banner & header badge in Layout
        • Sidebar nav entry "API Management"
        • Built: /app/admin/dist updated
      Mobile UI:
        • Home tab shows Demo Mode banner with count when any integration is in demo
      Test credentials in /app/memory/test_credentials.md (admin@mfb.in / Admin@MFB2026; demo@mfb.in / demo1234).
      Please verify:
        1) Admin login → /api-management → list, expand Stripe row, save fake key (sk_test_abcdefghijk1234567), test connection (will fail), then clear key. Verify status badge updates without page reload.
        2) Toggle force_demo on Razorpay → verify status="demo" even with key set.
        3) Disable a row → verify status="disabled" and mobile /api/app/api-status reflects it.
        4) Mobile (web preview): login as demo@mfb.in/demo1234 → home should show Demo Mode banner.
        5) Existing flows still work: wallet top-up (should auto-fallback to demo), stocks list (should still load with live cache), notifications, banners, KYC.

backend_v2:
  - task: "AI Investment Suggestions endpoint (ai_invest.py)"
    implemented: true
    working: true
    file: "/app/backend/ai_invest.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
        -working: true
        -agent: "main"
        -comment: "Uses Emergent LLM key + Claude Sonnet 4.6 to return personalised JSON with overall_summary, risk_score, risk_label, recommendations (buy/hold/sell + confidence + reason), suggested_sip, next_steps, disclaimer. Falls back to rule-based suggestion when LLM fails or key absent. Per-user cache (30 min) stored in MongoDB ai_suggestions collection. Manual curl tests passed: live mode returns rich Claude output in ~17s; cached call returns in 14ms with cached=true."

frontend_v2:
  - task: "Mobile: AI Investment Coach screen + teaser card"
    implemented: true
    working: true
    file: "/app/frontend/app/invest/ai-coach.tsx, /app/frontend/app/(tabs)/invest.tsx"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
        -working: true
        -agent: "main"
        -comment: "New /invest/ai-coach screen with purple-pink hero, Today's snapshot card, risk profile bar, recommendation cards (BUY/HOLD/SELL badges with confidence dots), suggested SIP card, next steps list, disclaimer, refresh button. Teaser card with gradient added to Invest > Portfolio tab. Verified visually — Claude generates real recommendations (RELIANCE/HDFCBANK/TCS as BUY with reasons)."

agent_communication_v2:
    -agent: "main"
    -message: |
      Built AI Investment Suggestions feature.
      Backend: /app/backend/ai_invest.py uses emergentintegrations LlmChat with claude-sonnet-4-6. Endpoint GET /api/invest/ai-suggestions (auth required), optional ?refresh=true. Per-user 30-min MongoDB cache. Rule-based fallback when LLM unavailable.
      Mobile: New screen /app/frontend/app/invest/ai-coach.tsx with hero, snapshot, recommendations, SIP card. Teaser card on Invest tab Portfolio view.
      Creds: demo@mfb.in / demo1234 (mobile); admin@mfb.in / Admin@MFB2026 (admin).
      Verify: (1) endpoint returns full JSON shape; (2) 2nd call cached=true <200ms; (3) ?refresh=true bypasses cache; (4) mobile teaser → AI Coach screen renders; (5) existing flows unaffected.

