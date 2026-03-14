# Create a Vapi assistant and link it to the phone number
$headers = @{
    "Authorization" = "Bearer b38df737-1dfd-46c1-aa31-6ff586b4cff3"
    "Content-Type"  = "application/json"
}

$webhookUrl = "https://wex-backend-449870075865.us-west1.run.app/api/voice/webhook"

# Build assistant config matching our backend's build_assistant_config output
$assistantBody = @{
    name = "Robin - WEx Warehouse Broker"
    model = @{
        provider = "google"
        model = "gemini-3-flash-preview"
        messages = @(
            @{
                role = "system"
                content = "You are Robin, a warehouse space broker at Warehouse Exchange. You help businesses find warehouse and industrial space. You sound like a friendly, knowledgeable real estate professional. Ask for the caller's name, their target city, square footage needed, and use type. Then use the search_properties tool to find matches."
            }
        )
        temperature = 0.7
    }
    voice = @{
        provider = "11labs"
        voiceId = "jBzLvP03992lMFEkj2kJ"
    }
    firstMessage = "Hey, thanks for calling Warehouse Exchange, this is Robin. Who am I speaking with?"
    server = @{
        url = $webhookUrl
    }
    endCallFunctionEnabled = $true
    recordingEnabled = $true
    silenceTimeoutSeconds = 30
    maxDurationSeconds = 600
} | ConvertTo-Json -Depth 10

Write-Host "Creating Vapi assistant..." -ForegroundColor Cyan

try {
    $assistant = Invoke-RestMethod -Uri "https://api.vapi.ai/assistant" -Headers $headers -Method Post -Body $assistantBody
    
    Write-Host "Assistant created successfully!" -ForegroundColor Green
    Write-Host "Assistant ID: $($assistant.id)"
    Write-Host "Name: $($assistant.name)"
    Write-Host ""
    
    # Now link the assistant to the phone number
    Write-Host "Linking assistant to phone number..." -ForegroundColor Cyan
    
    $phoneUpdateBody = @{
        assistantId = $assistant.id
    } | ConvertTo-Json
    
    $phoneNumberId = "bb4c3eb8-863e-4ca0-b5be-02b65556d94d"
    $updatedPhone = Invoke-RestMethod -Uri "https://api.vapi.ai/phone-number/$phoneNumberId" -Headers $headers -Method Patch -Body $phoneUpdateBody
    
    Write-Host "Phone number updated!" -ForegroundColor Green
    Write-Host "Phone: $($updatedPhone.number)"
    Write-Host "Assistant ID on phone: $($updatedPhone.assistantId)"
    Write-Host "Server URL on phone: $($updatedPhone.server.url)"
    Write-Host ""
    Write-Host "Assistant ID to save in VAPI_ASSISTANT_ID: $($assistant.id)" -ForegroundColor Yellow
    
} catch {
    Write-Host "Error: $($_.Exception.Message)" -ForegroundColor Red
    if ($_.ErrorDetails.Message) {
        Write-Host "Details: $($_.ErrorDetails.Message)"
    }
}
