
import { App } from "@modelcontextprotocol/ext-apps";

const app = new App({
  name: "Payment Approval",
  version: "1.0.0"
});

const $ = (id) => document.getElementById(id);

let payment = null;

function setStatus(message) {
  $("status").textContent = message;
}

function setButtonsEnabled(enabled) {
  $("approve").disabled = !enabled;
  $("reject").disabled = !enabled;
}

function parseToolResult(result) {
  console.log("[MCP APP] Tool result:", result);

  if (result?.isError) {
    throw new Error("Payment tool returned an error");
  }

  let data = result?.structuredContent;

  if (!data) {
    const text = result?.content?.find(
      (item) => item.type === "text"
    )?.text;

    if (text) {
      data = JSON.parse(text);
    }
  }

  // Some SDK responses wrap structured data in a result object.
  if (data?.result?.payment_id) {
    data = data.result;
  }

  return data;
}

function showPayment(data) {
  if (!data || !data.payment_id) {
    throw new Error("Invalid payment data received");
  }

  payment = data;

  $("amount").textContent =
    `${data.currency ?? "USD"} ${data.amount ?? "0.00"}`;

  $("account").textContent =
    data.account_id ?? "Unknown";

  $("recipient").textContent =
    data.recipient_id ?? "Unknown";

  $("payment-id").textContent = data.payment_id;

  $("payment-status").textContent =
    data.status ?? "Unknown";

  const pending = data.status === "pending_approval";

  setButtonsEnabled(pending);
  setStatus(
    pending
      ? "Payment is awaiting approval."
      : `Payment status: ${data.status}`
  );
}

// Called when the MCP host sends the tool result.
app.ontoolresult = (result) => {
  try {
    const data = parseToolResult(result);

    if (data) {
      showPayment(data);
    } else {
      setStatus("No payment details received.");
    }
  } catch (error) {
    console.error("[MCP APP] Tool result error:", error);
    setStatus(`Unable to load payment: ${error.message}`);
  }
};

// Demo-only buttons.
// They do not perform payment transactions.
$("approve").addEventListener("click", () => {
  if (!payment) return;

  setButtonsEnabled(false);
  setStatus("Approval selected (demo only).");
});

$("reject").addEventListener("click", () => {
  if (!payment) return;

  setButtonsEnabled(false);
  setStatus("Rejection selected (demo only).");
});

// Disable actions until valid data arrives.
setButtonsEnabled(false);

async function initialize() {
  try {
    setStatus("Connecting to MCP host...");

    console.log("[MCP APP] Starting connection");

    await app.connect();

    console.log("[MCP APP] Connected successfully");

    setStatus("Connected. Waiting for payment details...");
  } catch (error) {
    console.error("[MCP APP] Connection failed:", error);

    setStatus(
      `MCP App connection failed: ${error.message}`
    );
  }
}

initialize();
