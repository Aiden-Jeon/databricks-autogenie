/**
 * Step indicator component for multi-step workflows.
 * Works for both Lamp and Enhancer workflows.
 */

'use client';

interface StepperProps {
  currentStep: number;
  steps: string[];
}

export function Stepper({ currentStep, steps }: StepperProps) {
  return (
    <div className="flex items-center justify-between">
      {steps.map((step, index) => {
        const stepNumber = index + 1;
        const isCompleted = currentStep > stepNumber;
        const isActive = currentStep === stepNumber;

        return (
          <div key={step} className="flex items-center flex-1">
            {/* Step Circle */}
            <div className="flex flex-col items-center">
              <div
                className={`
                  w-10 h-10 rounded-full flex items-center justify-center font-semibold text-sm
                  ${isCompleted ? 'bg-green-500 text-white' : ''}
                  ${isActive ? 'bg-blue-500 text-white ring-4 ring-blue-200' : ''}
                  ${!isCompleted && !isActive ? 'bg-gray-200 text-gray-500' : ''}
                `}
              >
                {isCompleted ? '✓' : stepNumber}
              </div>
              <span
                className={`
                  mt-2 text-xs font-medium text-center max-w-[80px]
                  ${isActive ? 'text-blue-600' : 'text-gray-500'}
                `}
              >
                {step}
              </span>
            </div>

            {/* Connector Line */}
            {index < steps.length - 1 && (
              <div
                className={`
                  flex-1 h-0.5 mx-2
                  ${currentStep > stepNumber ? 'bg-green-500' : 'bg-gray-200'}
                `}
              />
            )}
          </div>
        );
      })}
    </div>
  );
}
