// Make QED boxes clickable to collapse/expand proofs
document.addEventListener('DOMContentLoaded', function() {
    const proofBoxes = document.querySelectorAll('.proof-box');

    proofBoxes.forEach(function(proofBox) {
        const qedBox = proofBox.querySelector('.qed-box');

        if (qedBox) {
            qedBox.addEventListener('click', function() {
                proofBox.classList.toggle('collapsed');
            });
        }
    });
});
