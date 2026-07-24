/**
 * Script: pagination_on
 * ID: c31e8cd1
 * Type: js_execute
 * Workflow: default
 * Created: 2026-07-20T16:28:58.733538
 * Description: goes to next page
 */

// ============================================================================
// Step Configuration
// ============================================================================

const stepConfig = {
    id: 'c31e8cd1',
    name: 'pagination_on',
    type: 'js_execute',
    timeout: 40,
    retryCount: 3,
    retryDelay: 1,
    continueOnError: false,
    metadata: {}
};

// ============================================================================
// Main Execution Function
// ============================================================================

async function execute(api, context) {
    console.log(`🔧 Executing step: ${stepConfig.name} (ID: ${stepConfig.id})`);

    try {
        (async function () {
            "use strict";

            const delay = ms => new Promise(r => setTimeout(r, ms));

            function currentPage() {
                const active = document.querySelector(
                    ".pagination-number li.active .number"
                );

                return active ? parseInt(active.textContent.trim(), 10) : null;
            }

            function pageButtons() {
                return [...document.querySelectorAll(
                    ".pagination-number .number"
                )];
            }

            async function waitForPageChange(oldPage) {
                for (let i = 0; i < 50; i++) {
                    await delay(200);

                    const now = currentPage();
                    if (now !== oldPage)
                        return true;
                }

                return false;
            }

            const current = currentPage();

            if (current == null) {
                console.error("Cannot determine current page.");
                return false;
            }

            const target = current + 1;

            console.log(`Current page : ${current}`);
            console.log(`Target page  : ${target}`);

            // -------------------------
            // Look for page n+1
            // -------------------------
            const targetButton = pageButtons().find(btn =>
                parseInt(btn.textContent.trim(), 10) === target
            );

            if (targetButton) {

                console.log(`Clicking page ${target}`);

                targetButton.click();

                await waitForPageChange(current);

                return {
                    success: true,
                    page: target
                };
            }

            // -------------------------
            // n+1 not visible
            // Try advancing pagination
            // -------------------------
            const nextGroup = document.querySelector(
                ".pagination-number .right-arrow.arrow:not(.disabled)"
            );

            if (!nextGroup) {
                console.log("No further pages.");
                return {
                    success: false,
                    reason: "last_page"
                };
            }

            console.log("Advancing pagination window...");

            nextGroup.click();

            await delay(1500);

            // Search again
            const retry = pageButtons().find(btn =>
                parseInt(btn.textContent.trim(), 10) === target
            );

            if (!retry) {
                console.log(`Page ${target} still not found.`);
                return {
                    success: false,
                    reason: "page_not_found"
                };
            }

            console.log(`Clicking page ${target}`);

            retry.click();

            await waitForPageChange(current);

            return {
                success: true,
                page: target
            };

        })();
    } catch (error) {
        console.error(`❌ Step failed: ${error.message}`);
        if (stepConfig.continueOnError) {
            console.warn(`⚠️ Continuing despite error`);
            return { error: error.message, step: stepConfig.name };
        }
        throw error;
    }
}

// Export for workflow engine
if (typeof module !== 'undefined' && module.exports) {
    module.exports = { execute, stepConfig };
}

