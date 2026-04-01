import React, { useState, useEffect } from "react";

interface CountdownTimerProps {
    endTime: string;
    delayText: string;
    children?: React.ReactNode
}

const CountdownTimer: React.FC<CountdownTimerProps> = ({ endTime, delayText, children }) => {
    // get endTime as a Date object for comparison
    const end = new Date(endTime);

    const [isDelayed, setIsDelayed] = useState(false);
    const [remainingSeconds, setRemainingSeconds] = useState(0);

    useEffect(() => {
        let intervalId: NodeJS.Timer | null = null;

        function updateState() {
            const now = new Date();
            const diff = end.getTime() - now.getTime();

            if (diff <= 0) {
                if (intervalId !== null) {
                    clearInterval(intervalId);
                }
                setIsDelayed(true);
            } else {
                setRemainingSeconds(Math.floor(diff / 1000));
            }
        }

        updateState();

        if (!isDelayed) {
            intervalId = setInterval(updateState, 1000);
        }

        return () => { intervalId !== null && clearInterval(intervalId) };
    }, [remainingSeconds, isDelayed]);

    return (
        <div className="container mb-3 bg-light">
            <div className="p-3">
                {
                    isDelayed ? (
                        <p>{delayText}</p>
                    ) : (
                        remainingSeconds > 0 &&
                        <>
                            <h5>Estimated time to complete:</h5>
                            <h2>{remainingSeconds}s left</h2>
                        </>
                    )
                }
                {children}
            </div>
        </div>
    );
};

export default CountdownTimer;
