import { AlertTriangle, CheckCircle2, CreditCard, RefreshCw } from "lucide-react";
import type { BillingSummary } from "../api/types";

type Props = {
  billing: BillingSummary | null;
  loading: boolean;
  error: string;
  onRefresh: () => void;
};

function formatDate(epoch?: number | null) {
  if (!epoch) return "Not set";
  return new Date(epoch * 1000).toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

function formatLimit(limit: number | null) {
  return limit === null ? "Unlimited" : `${limit}`;
}

function planTone(planId: string) {
  if (planId === "pro") return "pro";
  if (planId === "enterprise") return "enterprise";
  if (planId === "starter") return "starter";
  return "trial";
}

export function BillingPanel({ billing, loading, error, onRefresh }: Props) {
  if (!billing) {
    return (
      <section className="billing-page">
        <div className="panel billing-empty">
          <CreditCard size={26} />
          <div>
            <h3>Billing & Plan</h3>
            <p>{error || "Load billing to view plan and usage."}</p>
          </div>
          <button onClick={onRefresh} disabled={loading}>
            <RefreshCw size={16} /> {loading ? "Loading" : "Load billing"}
          </button>
        </div>
      </section>
    );
  }

  const currentPlanId = billing.currentPlan.id;
  const usage = billing.usage;
  const gatewayReady = billing.paymentGateway.configured;

  return (
    <section className="billing-page">
      <div className="billing-header-row">
        <div>
          <p className="eyebrow">Billing & Plan</p>
          <h3>{billing.organization.orgName}</h3>
        </div>
        <button className="secondary-btn" onClick={onRefresh} disabled={loading}>
          <RefreshCw size={16} /> Refresh
        </button>
      </div>

      {error && <div className="login-status error">{error}</div>}

      <div className="billing-summary-grid">
        <div className={`billing-summary-card ${planTone(currentPlanId)}`}>
          <span>Current Plan</span>
          <strong>{billing.currentPlan.name}</strong>
          <em>{billing.currentPlan.status}</em>
        </div>
        <div className="billing-summary-card">
          <span>Interviews Used</span>
          <strong>{usage.used}/{formatLimit(usage.limit)}</strong>
          <em>{usage.currentMonth}</em>
        </div>
        <div className="billing-summary-card">
          <span>Remaining</span>
          <strong>{usage.remaining === null ? "Unlimited" : usage.remaining}</strong>
          <em>{usage.usagePercent}% used</em>
        </div>
        <div className="billing-summary-card">
          <span>Payment Gateway</span>
          <strong>Razorpay</strong>
          <em>{gatewayReady ? "Configured" : "Pending setup"}</em>
        </div>
      </div>

      <div className="usage-progress-track">
        <div style={{ width: `${Math.min(100, usage.usagePercent)}%` }} />
      </div>

      {!gatewayReady && (
        <div className="billing-alert">
          <AlertTriangle size={18} />
          <span>Razorpay keys are not configured in SSM yet. Plan upgrades stay locked until payment setup is ready.</span>
        </div>
      )}

      <div className="billing-section-title">
        <h3>Plans</h3>
        <p>Trial, Starter, Pro, and Enterprise quotas</p>
      </div>

      <div className="plan-grid">
        {billing.plans.map((plan) => {
          const isCurrent = plan.id === currentPlanId;
          return (
            <article className={`plan-tile ${plan.popular ? "popular" : ""}`} key={plan.id}>
              {plan.popular && <span className="plan-badge">Most popular</span>}
              <div className="plan-title-row">
                <h4>{plan.name}</h4>
                {isCurrent && <span className="current-plan-pill"><CheckCircle2 size={14} /> Current</span>}
              </div>
              <strong>{plan.priceLabel}</strong>
              <p>{formatLimit(plan.monthlyInterviewLimit)} interviews/month</p>
              <ul>
                {plan.features.map((feature) => <li key={feature}>{feature}</li>)}
              </ul>
              <button disabled className={isCurrent ? "secondary-btn" : ""}>
                {isCurrent ? "Current plan" : gatewayReady ? "Checkout coming next" : "Payment setup pending"}
              </button>
            </article>
          );
        })}
      </div>

      <div className="billing-section-title">
        <h3>Subscription History</h3>
        <p>Latest account and plan events</p>
      </div>

      <div className="billing-history">
        {billing.events.length === 0 && (
          <div className="history-empty">No billing events yet.</div>
        )}
        {billing.events.map((event) => (
          <div className="billing-history-row" key={event.eventId}>
            <span className={`history-dot ${event.eventType}`} />
            <div>
              <strong>{event.label}</strong>
              <p>{[event.oldPlan, event.newPlan].filter(Boolean).join(" -> ") || event.newPlan || "Plan event"}</p>
            </div>
            <time>{formatDate(event.createdAt)}</time>
          </div>
        ))}
      </div>
    </section>
  );
}
