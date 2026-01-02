document.addEventListener('DOMContentLoaded', () => {
    const proofDetails = document.querySelectorAll('details.proof-box');
    const collapsedMessages = [
        ' (left as an exercise to the reader)',
        ' (just trust me bro)',
        ' (trivial)',
    ];
    let messageIndex = 0;

    proofDetails.forEach(details => {
        const summary = details.querySelector('summary');
        if (!summary) return;

        summary.style.cursor = 'pointer';

        const toggleTextSpan = summary.querySelector('.proof-toggle-text');
        if (!toggleTextSpan) return;

        const updateText = () => {
            if (details.open) {
                toggleTextSpan.textContent = ' (hide)';
            } else {
                toggleTextSpan.textContent = collapsedMessages[messageIndex];
                messageIndex = (messageIndex + 1) % collapsedMessages.length;
            }
        };

        // Set initial text
        updateText();

        // Add event listener for toggling
        details.addEventListener('toggle', updateText);
    });
});
