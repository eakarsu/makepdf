/**
 * MakePDF - Shared frontend utilities
 */

function showAlert(msg, type) {
    const el = document.getElementById("alert");
    el.textContent = msg;
    el.className = "alert " + type;
}

function hideAlert() {
    const el = document.getElementById("alert");
    el.className = "alert hidden";
}

/**
 * Submit a form via fetch. Handles file downloads and JSON responses.
 * @param {HTMLFormElement} form
 * @param {object} opts - { onJson: fn(data), filename: string }
 */
async function submitForm(form, opts = {}) {
    const btn = form.querySelector('button[type="submit"]');
    const origText = btn.textContent;
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner"></span>Processing...';
    hideAlert();

    try {
        const resp = await fetch(form.action, {
            method: "POST",
            body: new FormData(form),
        });

        if (!resp.ok) {
            let errMsg;
            try {
                const data = await resp.json();
                errMsg = data.error || data.detail || JSON.stringify(data);
            } catch {
                errMsg = await resp.text();
            }
            showAlert(errMsg, "error");
            return;
        }

        const ct = resp.headers.get("content-type") || "";

        if (ct.includes("application/json")) {
            const data = await resp.json();
            if (opts.onJson) {
                opts.onJson(data);
            } else {
                showAlert(JSON.stringify(data, null, 2), "success");
            }
        } else {
            // File download
            const blob = await resp.blob();
            const url = URL.createObjectURL(blob);
            const a = document.createElement("a");
            a.href = url;
            // Try to get filename from content-disposition header
            const cd = resp.headers.get("content-disposition") || "";
            const match = cd.match(/filename="?([^";\n]+)"?/);
            a.download = match ? match[1] : (opts.filename || "output.pdf");
            document.body.appendChild(a);
            a.click();
            a.remove();
            URL.revokeObjectURL(url);
            showAlert("Download started!", "success");
        }
    } catch (err) {
        showAlert("Request failed: " + err.message, "error");
    } finally {
        btn.disabled = false;
        btn.textContent = origText;
    }
}

// Auto-bind forms with data-async attribute
document.addEventListener("DOMContentLoaded", () => {
    document.querySelectorAll("form[data-async]").forEach((form) => {
        form.addEventListener("submit", (e) => {
            e.preventDefault();
            const jsonTarget = form.dataset.jsonTarget;
            submitForm(form, {
                filename: form.dataset.filename || "output.pdf",
                onJson: jsonTarget
                    ? (data) => {
                          const el = document.getElementById(jsonTarget);
                          if (el) {
                              el.textContent = JSON.stringify(data, null, 2);
                              el.classList.remove("hidden");
                          }
                      }
                    : null,
            });
        });
    });
});
