const main = () => {
	const ptr = document.getElementById("ptr");
	if (!ptr) {
		return;
	}

	const threshold = 70; // px
	let startY = 0;
	let active = false;

	const scrollTop = () =>
		document.scrollingElement?.scrollTop ?? window.scrollY ?? 0;

	window.addEventListener(
		"touchstart",
		(e) => {
			if (scrollTop() > 0) return;
			startY = e.touches[0].clientY;
			active = true;
		},
		{ passive: true }
	);

	window.addEventListener(
		"touchmove",
		(e) => {
			if (!active) return;
			if (scrollTop() > 0) {
				active = false;
				return;
			}

			const dy = e.touches[0].clientY - startY;
			if (dy > 10) {
				ptr.style.display = "flex";
				ptr.textContent = dy > threshold ? "Release to refresh…" : "Pull to refresh…";
			}
		},
		{ passive: true }
	);

	window.addEventListener(
		"touchend",
		(e) => {
			if (!active) return;
			active = false;

			const endY = e.changedTouches?.[0]?.clientY ?? startY;
			const dy = endY - startY;

			if (ptr.style.display === "flex" && dy > threshold) {
				ptr.textContent = "Refreshing…";
				window.location.reload();
			} else {
				ptr.style.display = "none";
			}
		},
		{ passive: true }
	);
};

main();
