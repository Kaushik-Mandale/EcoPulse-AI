import React, { useRef, useEffect } from 'react';

const OtpInput = ({ value = '', onChange, disabled = false, autoFocus = true }) => {
  const inputRefs = useRef([]);

  // Ensure digits array always has 6 items
  const digits = Array.from({ length: 6 }, (_, i) => value[i] || '');

  useEffect(() => {
    if (autoFocus && inputRefs.current[0] && !disabled) {
      inputRefs.current[0].focus();
    }
  }, [autoFocus, disabled]);

  const handleChange = (index, e) => {
    const val = e.target.value.replace(/\D/g, '');
    if (!val) {
      // Empty input
      const newDigits = [...digits];
      newDigits[index] = '';
      onChange(newDigits.join(''));
      return;
    }

    // Single digit entered
    const digit = val[val.length - 1]; // take last entered digit
    const newDigits = [...digits];
    newDigits[index] = digit;
    const combined = newDigits.join('');
    onChange(combined);

    // Auto focus next input
    if (index < 5 && inputRefs.current[index + 1]) {
      inputRefs.current[index + 1].focus();
    }
  };

  const handleKeyDown = (index, e) => {
    if (e.key === 'Backspace') {
      if (!digits[index] && index > 0 && inputRefs.current[index - 1]) {
        // Current box is empty, move back and clear previous
        inputRefs.current[index - 1].focus();
        const newDigits = [...digits];
        newDigits[index - 1] = '';
        onChange(newDigits.join(''));
      }
    } else if (e.key === 'ArrowLeft' && index > 0) {
      inputRefs.current[index - 1].focus();
    } else if (e.key === 'ArrowRight' && index < 5) {
      inputRefs.current[index + 1].focus();
    }
  };

  const handlePaste = (e) => {
    e.preventDefault();
    const pastedData = e.clipboardData.getData('text').replace(/\D/g, '').slice(0, 6);
    if (pastedData) {
      onChange(pastedData);
      const nextFocus = Math.min(pastedData.length, 5);
      if (inputRefs.current[nextFocus]) {
        inputRefs.current[nextFocus].focus();
      }
    }
  };

  return (
    <div className="flex items-center justify-between gap-1.5 sm:gap-2 my-2" onPaste={handlePaste}>
      {Array.from({ length: 6 }).map((_, i) => (
        <input
          key={i}
          ref={(el) => (inputRefs.current[i] = el)}
          type="text"
          inputMode="numeric"
          pattern="[0-9]*"
          maxLength={1}
          value={digits[i]}
          onChange={(e) => handleChange(i, e)}
          onKeyDown={(e) => handleKeyDown(i, e)}
          disabled={disabled}
          className={`w-10 sm:w-12 h-12 sm:h-13 text-center text-lg sm:text-xl font-black rounded-xl border transition-all outline-none select-none ${
            digits[i]
              ? 'border-[#16a34a] bg-emerald-50/50 text-[#16a34a] ring-2 ring-emerald-100 shadow-xs'
              : 'border-slate-300 bg-white text-slate-800 focus:border-[#16a34a] focus:ring-2 focus:ring-emerald-100'
          } ${disabled ? 'opacity-60 cursor-not-allowed bg-slate-100' : 'cursor-text'}`}
        />
      ))}
    </div>
  );
};

export default OtpInput;
