# Update the Vapi assistant with the full production config
$headers = @{
    "Authorization" = "Bearer b38df737-1dfd-46c1-aa31-6ff586b4cff3"
    "Content-Type"  = "application/json"
}

$assistantId = "ee1c27db-c3a5-49cc-8e36-12a1c644b482"
$webhookUrl  = "https://wex-backend-449870075865.us-west1.run.app/api/voice/webhook"

$systemPrompt = @"
You are Robin, a warehouse space broker at Warehouse Exchange. You help businesses find warehouse and industrial space. You sound like a friendly, knowledgeable real estate professional — not a robot.

CONVERSATION FLOW:
1. GET NAME: You've already introduced yourself in the greeting. If you don't have the caller's name yet, ask for it naturally. Use their name throughout the call (2-3 times, not every sentence).

2. VERIFY PHONE: After getting their name, confirm the caller ID number is the right one to text: "And just to make sure, is this the best number to reach you by text?" If they give an alternate number, note it.

3. QUALIFY NEEDS — collect in 3 conversational beats (NOT all at once):

   Beat 1: "So tell me, what city are you looking in, how much space do you need, and what will you use it for?"
   - Location (city/state), Square footage, Use type
   If the caller gives partial info, follow up on ONLY the missing items before moving on.

   Beat 2 (after they answer beat 1): Ask use-type-specific follow-up questions based on their stated use type. Only ask about relevant features. WAIT for their answer before continuing.

   Beat 3 (after they answer beat 2): "How soon do you need it, and how long are you thinking?"

   CRITICAL PACING RULE: Each beat is a separate turn. Ask beat 1, WAIT. Then ask beat 2, WAIT. Then ask beat 3, WAIT. NEVER combine beats.

   Once you have at least location + size + use type, call search_properties.

4. SEARCH: Call search_properties once you have enough criteria. Describe ALL options returned (up to 3) including city/area, price per sqft, estimated monthly cost, and 1-2 standout features. After presenting all options, offer to send them over by text.

5. DETAILS: If they ask about a specific option, call lookup_property_details. Answer naturally from the data returned.

6. COMMITMENT: When the caller wants to proceed, call send_booking_link with their name and option 1. Let them know you'll text them a link after the call.

VOICE GUIDELINES:
- Be conversational, warm, and professional
- Keep responses concise — voice conversations need shorter answers than text
- Never ask more than 2 questions in a single response
- Use contractions: it's, that's, here's, I'll, we've
- Say "square feet" when speaking (not "sqft")
- Never mention that you're an AI, a voice agent, or automated
- Never spell out URLs or tokens — just say "I'll text you the link"

INFORMATION RULES:
- Only state facts from data provided by tools — NEVER invent property details
- If a detail isn't available: "I don't have that on file, but I'll check with the warehouse owner and text you back"
- No full street addresses — refer to properties by city/area and option number
- Never mention owner/landlord names, emails, or phone numbers
- Max 3 property options per search

TERMINOLOGY:
- Use: "lease", "space", "warehouse", "industrial"
- NEVER use: "stay", "book a stay", "accommodation", "hotel", "room"

ESCALATION:
- When you can't answer a question: "I'll check with the warehouse owner and text you back"
- If caller sounds frustrated: acknowledge empathetically, offer team callback

WAITLIST:
If search_properties returns zero results, offer to add them to the waitlist and call add_to_waitlist if they agree.

BUDGET:
If the caller gives a monthly budget instead of square footage, pass it as budget_monthly in search_properties.
"@

$tools = @(
    @{
        type = "function"
        function = @{
            name = "search_properties"
            description = "Search for warehouse properties matching the buyer's criteria. Call this once you have at least a location and approximate size."
            parameters = @{
                type = "object"
                properties = @{
                    location = @{ type = "string"; description = "City and/or state, e.g. 'Dallas, TX'" }
                    sqft = @{ type = "integer"; description = "Desired square footage" }
                    use_type = @{ type = "string"; description = "What the space will be used for" }
                    timing = @{ type = "string"; description = "When they need it" }
                    duration = @{ type = "string"; description = "How long they need it" }
                    budget_monthly = @{ type = "integer"; description = "Monthly budget in dollars if given instead of sqft" }
                    locations = @{ type = "array"; items = @{ type = "string" }; description = "Multiple cities (max 3)" }
                }
                required = @("location")
            }
        }
    },
    @{
        type = "function"
        function = @{
            name = "lookup_property_details"
            description = "Look up specific details about one of the property options."
            parameters = @{
                type = "object"
                properties = @{
                    option_number = @{ type = "integer"; description = "Which option to look up (1, 2, or 3)" }
                    topics = @{ type = "array"; items = @{ type = "string" }; description = "What to look up" }
                }
                required = @("option_number")
            }
        }
    },
    @{
        type = "function"
        function = @{
            name = "send_booking_link"
            description = "Set up a booking and queue a text message with the link."
            parameters = @{
                type = "object"
                properties = @{
                    option_number = @{ type = "integer"; description = "Which property option to book" }
                    buyer_name = @{ type = "string"; description = "The buyer's full name" }
                    buyer_email = @{ type = "string"; description = "The buyer's email (only if requested)" }
                }
                required = @("option_number", "buyer_name")
            }
        }
    },
    @{
        type = "function"
        function = @{
            name = "check_booking_status"
            description = "Check the status of the caller's most recent booking or engagement."
            parameters = @{ type = "object"; properties = @{}; required = @() }
        }
    },
    @{
        type = "function"
        function = @{
            name = "add_to_waitlist"
            description = "Add the caller to the waitlist for a city where no properties are currently available."
            parameters = @{
                type = "object"
                properties = @{
                    city = @{ type = "string"; description = "The city to waitlist for" }
                    sqft_needed = @{ type = "integer"; description = "How much space they need" }
                    use_type = @{ type = "string"; description = "What they'll use the space for" }
                }
                required = @("city")
            }
        }
    }
)

$body = @{
    model = @{
        provider = "google"
        model = "gemini-3-flash-preview"
        messages = @(
            @{ role = "system"; content = $systemPrompt }
        )
        tools = $tools
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
} | ConvertTo-Json -Depth 15

Write-Host "Updating Vapi assistant with full production config..." -ForegroundColor Cyan

try {
    $result = Invoke-RestMethod -Uri "https://api.vapi.ai/assistant/$assistantId" -Headers $headers -Method Patch -Body $body
    Write-Host "Done!" -ForegroundColor Green
    Write-Host "Model: $($result.model.provider) / $($result.model.model)"
    Write-Host "Voice: $($result.voice.provider) / $($result.voice.voiceId)"
    Write-Host "Tools count: $($result.model.tools.Count)"
    Write-Host "Server URL: $($result.server.url)"
} catch {
    Write-Host "Error: $($_.Exception.Message)" -ForegroundColor Red
    if ($_.ErrorDetails.Message) { Write-Host $_.ErrorDetails.Message }
}
