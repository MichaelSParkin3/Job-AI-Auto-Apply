# SimplyHired Snippets

Collected HTML snippets captured from SimplyHired to guide scraper implementations.

## SimplyHired Job Card List & Quick Apply

```html
<div class="css-in8ucq">
  <div class="css-12595yo">
    <ul role="list" id="job-list" class="css-13ia03s">
      <li class="css-0">
        <div data-testid="searchSerpJob" data-jobkey="EE0JMn0RJ12T…" class="css-1inpap1">
          <h2 data-testid="searchSerpJobTitle">
            <a class="chakra-button css-16lgz6b" href="/job/EE0JMn0R…">Power App Developer</a>
          </h2>
          <p data-testid="searchSerpJobQuickApply" class="css-u40boz">Quick Apply</p>
          <div class="css-2imjyh">
            <p data-testid="searchSerpJobSalaryConfirmed" class="css-1g1y608">$18 an hour</p>
            <p data-testid="searchSerpJobDateStamp" class="css-5yilgw">3h</p>
          </div>
        </div>
      </li>
      …
    </ul>
    <nav role="navigation" aria-label="pagination">
      <ul data-testid="pageNumberContainer" class="css-1deteqx">
        <li class="css-15j46vp">
          <a class="chakra-link css-16mmgjw" data-testid="pageNumberBlockPrevious" href="…">
            <svg class="svg-inline--fa fa-chevron-left"></svg>
          </a>
        </li>
        <li class="css-z7hu84">
          <span class="chakra-link css-1vdegr" data-testid="paginationBlock2" aria-current="true">2</span>
        </li>
        <li class="css-1a0hv72">
          <a class="chakra-link css-16mmgjw" data-testid="pageNumberBlockNext" href="…">
            <svg class="svg-inline--fa fa-chevron-right"></svg>
          </a>
        </li>
      </ul>
    </nav>
  </div>
</div>
```

**Detection guidance**
- Use `li div[data-testid="searchSerpJob"]` as the primary card selector; `data-jobkey` uniquely identifies each posting.
- `p[data-testid="searchSerpJobQuickApply"]` contains the literal "Quick Apply" label when fast apply is supported—set `hasEasyApply = True` when present.
- Salary and age metadata live under `.css-2imjyh` via `data-testid="searchSerpJobSalaryConfirmed"` and `data-testid="searchSerpJobDateStamp"`.
- Pagination controls sit inside `ul[data-testid="pageNumberContainer"]`; `data-testid="pageNumberBlockNext"`/`Previous` yield the navigation anchors, so scrape the `href` to continue fetching additional result pages.

## SimplyHired Quick Apply Button (Detail View)

```html
<a class="chakra-button css-24yw96"
   data-testid="viewJobHeaderFooterApplyButton"
   rel="nofollow"
   href="/out?r=...">
  <div class="css-70qvj9">
    <svg class="svg-inline--fa fa-bolt-lightning css-20e7ar" aria-label="Quick Apply Available"></svg>
    <p class="chakra-text css-0">Quick Apply</p>
  </div>
</a>
```

**Detection guidance**
- In the job detail pane, reuse the same anchor selector to confirm Quick Apply availability; capture the outbound `href` for logging.
- When both list card and detail pane indicate Quick Apply, prefer the job detail target URL for launching the automation.

## SimplyHired Job List (SERP)

```html
<div class="css-in8ucq"><div class="css-12595yo"><ul role="list" id="job-list" tabindex="-1" class="css-13ia03s"><li class="css-0"><div data-jobkey="nMaRN9nEZNKT2B2nrxvJGide1jsUjRR4iA8yLCVh4C_x_nn5Ais7HQ" role="presentation" data-testid="searchSerpJob" class="css-1ijdc8n">...</div></li></ul>...<nav role="navigation" aria-label="pagination" style="width: 100%;"><ul role="list" data-testid="pageNumberContainer" class="css-1deteqx">...<a class="chakra-link css-16mmgjw" aria-label="Next page" data-testid="pageNumberBlockNext" href="...">...</a></li></ul></nav>...</div></div>
```

**Detection guidance**
- Job card selector: `div[data-testid="searchSerpJob"]`
- Job key: `data-jobkey` attribute.
- Title: `h2[data-testid="searchSerpJobTitle"] a`
- Company: `span[data-testid="companyName"]`
- Location: `span[data-testid="searchSerpJobLocation"]`
- Quick Apply indicator: `p[data-testid="searchSerpJobQuickApply"]`
- Pagination container: `nav[aria-label="pagination"]`
- Next page button: `a[data-testid="pageNumberBlockNext"]`

## SimplyHired Job Detail Panel

```html
<div class="flex-container css-p1d28v">
    <aside aria-label="Application Development & Maintenance – ADM" class="css-nzjs22">
        <h2 class="chakra-heading css-yvgnf2" data-testid="viewJobTitle">Application Development & Maintenance – ADM</h2>
        <a class="chakra-button css-24yw96" data-testid="viewJobHeaderFooterApplyButton" ...>
            <p class="chakra-text css-0">Quick Apply</p>
        </a>
        <div data-testid="viewJobQualificationsContainer" class="css-0">
            <span data-testid="viewJobQualificationItem" class="css-p3sbg2">Node.js</span>
        </div>
        <div data-testid="viewJobBodyJobFullDescriptionContent" class="css-cxpe4v">...</div>
    </aside>
</div>
```

**Detection guidance**
- Panel container: `aside.css-nzjs22`
- Title: `h2[data-testid="viewJobTitle"]`
- Quick Apply Button: `a[data-testid="viewJobHeaderFooterApplyButton"]`
- Qualifications: `span[data-testid="viewJobQualificationItem"]`
- Full Description: `div[data-testid="viewJobBodyJobFullDescriptionContent"]`

## SimplyHired Apply Modal - Location Step

```html
<div class="css-1lqx5xq e37uo190">
    <h2 data-testid="profile-location-heading" class="mosaic-provider-module-apply-contact-info-hsxxsf e1tiznh50">Review your location details from your profile</h2>
    <input aria-invalid="false" data-testid="location-fields-postal-code-input" id="location-fields-postal-code-input" ...>
    <input type="text" ... data-testid="location-fields-locality-input" id="location-fields-locality-input" ...>
    <button type="button" data-testid="continue-button" class="mosaic-provider-module-apply-contact-info-1jjpjay e8ju0x50"><span>Continue</span></button>
</div>
```

**Detection guidance**
- Heading: `h2[data-testid="profile-location-heading"]`
- Zip Code Input: `input[data-testid="location-fields-postal-code-input"]`
- City/State Input: `input[data-testid="location-fields-locality-input"]`
- Continue Button: `button[data-testid="continue-button"]`

## SimplyHired Apply Modal - Resume Selection

```html
<div data-testid="root-route" class="mosaic-provider-module-apply-resume-selection-s3c942 eu4oa1w0">
    <h1 class="mosaic-provider-module-apply-resume-selection-1d83m7w e1tiznh50">Choose how to apply</h1>
    <div data-testid="resume-selection-structured-resume-radio-card" ...>...</div>
    <button type="button" data-testid="resume-selection-file-resume-upload-button" ...>
        <span>Upload a resume</span>
    </button>
    <input type="file" data-testid="resume-selection-file-resume-upload-button-file-input" ...>
    <div data-testid="resume-selection-file-resume-radio-card" ...>...</div>
    <button type="button" data-testid="continue-button" ...><span>Continue</span></button>
</div>
```

**Detection guidance**
- Use Indeed Resume button: `div[data-testid="resume-selection-structured-resume-radio-card"]`
- Upload resume button: `button[data-testid="resume-selection-file-resume-upload-button"]`
- Hidden file input: `input[data-testid="resume-selection-file-resume-upload-button-file-input"]`
- Selected resume card: `div[data-testid="resume-selection-file-resume-radio-card"]`
- Continue button: `button[data-testid="continue-button"]`

## SimplyHired Apply Modal - Relevant Experience

```html
<div class="mosaic-provider-module-apply-resume-2xt5og eu4oa1w0">
    <h2 class="mosaic-provider-module-apply-resume-lsxcn7 e1tiznh50">Enter a job that shows relevant experience</h2>
    <input type="text" ... data-testid="job-title-input" ...>
    <input type="text" ... data-testid="company-name-input" ...>
    <button type="button" data-testid="continue-button" ...><span>Continue</span></button>
</div>
```

**Detection guidance**
- Job Title input: `input[data-testid="job-title-input"]`
- Company Name input: `input[data-testid="company-name-input"]`
- Continue button: `button[data-testid="continue-button"]`

## SimplyHired Apply Modal - Review Application

```html
<div class="ia-BasePage ia-Review">
    <h1 class="ia-BasePage-heading dd-privacy-allow">Please review your application</h1>
    <div data-testid="fullName">Michael Parkin</div>
    <div data-testid="email">MichaelSParkin3@gmail.com</div>
    <div data-testid="location-city">Hollister, CA</div>
    <div data-testid="phoneNumber">+1 831 205 1786</div>
    <button class="aa7d94905790b41c9952be30b5ffa3616 css-hu4r59 e8ju0x50"><span>Submit your application</span></button>
</div>
```

**Detection guidance**
- Full Name value: `div[data-testid="fullName"]`
- Email value: `div[data-testid="email"]`
- Location value: `div[data-testid="location-city"]`
- Phone Number value: `div[data-testid="phoneNumber"]`
- Submit button: `button.css-hu4r59` (Note: This class is likely dynamic; prefer a more stable selector if available, like text content or position relative to the heading).

## SimplyHired Apply Modal - Custom Employer Questions

```html
<div class="ia-Questions mosaic-provider-module-apply-questions-u74ql7 eu4oa1w0">
    <h1 data-testid="questions-heading" class="mosaic-provider-module-apply-questions-lsxcn7 e1tiznh50">Answer these questions from the employer</h1>
    <div id="q_0" class="ia-Questions-item ...">
        <div data-testid="input-q_a11b2b3b8becb1b2b6d5b32a739cec18">
            <label for="rich-text-question-input-:r2:">
                <span data-testid="rich-text"><span>Desired Pay</span></span>
            </label>
            <textarea ... id="rich-text-question-input-:r2:" name="q_a11b2b3b8becb1b2b6d5b32a739cec18"></textarea>
        </div>
    </div>
    <div id="q_1" class="ia-Questions-item ...">
        <div data-testid="input-q_1526a69b63d160a72da37d466d21241a">
            <label for="date-question-input-:r5:">
                <span data-testid="rich-text"><span>Date Available</span></span>
            </label>
            <input placeholder="MM/DD/YYYY" id="date-question-input-:r5:" name="q_1526a69b63d160a72da37d466d21241a" ...>
        </div>
    </div>
    <div id="q_2" class="ia-Questions-item ...">
        <div data-testid="input-q_093f65e080a295f8076b1c5722a46aa2">
            <label for="text-question-input-:r8:">
                <span data-testid="rich-text"><span>Are you experienced with using Blackbaud Content Management System?</span></span>
                <span data-testid="input-q_093f65e080a295f8076b1c5722a46aa2-label-required-text">(Required)</span>
            </label>
            <input data-testid="input-q_093f65e080a295f8076b1c5722a46aa2-input" type="text" ...>
        </div>
    </div>
    <button type="button" data-testid="continue-button" ...><span>Continue</span></button>
</div>
```

**Detection guidance**
- **General Strategy:** Questions are dynamic. The most reliable way to answer a specific question is to first locate its `label` by text content, then find the `input` or `textarea` associated with it (often via the `for` attribute).
- Main container: `div.ia-Questions`
- Heading: `h1[data-testid="questions-heading"]`
- Question block selector: `div.ia-Questions-item` or more specifically `div[data-testid^="input-q_"]`.
- **Example ("Desired Pay"):**
  1. Find the `span` with the text "Desired Pay".
  2. Traverse up to the `label` and get its `for` attribute.
  3. Find the `textarea` with the matching `id`.
- **Example ("Blackbaud"):**
  1. Find the `span` with the text "Are you experienced with using Blackbaud...".
  2. Traverse up to the parent `div[data-testid^="input-q_"]`.
  3. Find the `input[data-testid$="-input"]` within that div.
- Continue button: `button[data-testid="continue-button"]`

## SimplyHired Apply Modal - Custom Questions (Variant)

```html
<div class="css-5nnpq8 eu4oa1w0">
    <div class="ia-Navigation-backContainer--wideScreen css-1p6k5ei e37uo190"><button class="ia-Navigation-back css-5bo663 e8ju0x50" aria-label="Go back">...</button></div>
    <div class="ia-Navigation-exit css-1wkg96z eu4oa1w0"><button data-testid="ExitLinkWithModalComponent-exitButton" class="css-1ry3a7b e8ju0x50"><span>Exit</span></button></div>
    <div class="ia-Questions mosaic-provider-module-apply-questions-u74ql7 eu4oa1w0">
        <h1 data-testid="questions-heading">Answer these questions from the employer</h1>
        
        <!-- Text Input -->
        <div data-testid="input-q_64537f6e6c3be8d8408f39284f7ef790">
            <label><span data-testid="input-q_64537f6e6c3be8d8408f39284f7ef790-label"><span>LinkedIn Profile</span></span></label>
            <input data-testid="input-q_64537f6e6c3be8d8408f39284f7ef790-input" type="text" ...>
        </div>

        <!-- Radio Group -->
        <div data-testid="input-q_a9ea45bbffc1930953da1c8752238e73">
            <label><span data-testid="input-q_a9ea45bbffc1930953da1c8752238e73-label"><span>How did you hear about Honor?</span></span></label>
            <label for="single-select-question-:r5:-1"><input id="single-select-question-:r5:-1" type="radio" value="212563589002" ...><span>Current Employee (Referral)</span></label>
        </div>

        <!-- Select/Dropdown -->
        <div data-testid="input-q_4d52c72489f0460bc3bb98fe51663e50">
            <label><span data-testid="input-q_4d52c72489f0460bc3bb98fe51663e50-label"><span>What state will you be working/residing in?</span></span></label>
            <select data-testid="input-q_4d52c72489f0460bc3bb98fe51663e50-select" ...>
                <option label="AL" value="212563594002">AL</option>
                ...
            </select>
        </div>
        <button type="button" data-testid="continue-button"><span>Continue</span></button>
    </div>
</div>
```

**Detection guidance**
- **General Strategy:** The `data-testid` attributes are the most stable selectors. Identify the question by its label text within the `div[data-testid^="input-q_"]` container, then target the specific input field.
- **Back Button:** `button.ia-Navigation-back`
- **Exit Button:** `button[data-testid="ExitLinkWithModalComponent-exitButton"]`
- **Text Input ("LinkedIn Profile"):** Target `input[data-testid="input-q_64537f6e6c3be8d8408f39284f7ef790-input"]`.
- **Radio Group ("How did you hear about Honor?"):** To select an option, find the `label` with the desired text (e.g., "Indeed") and click the `input` element inside it.
- **Select/Dropdown ("What state..."):** Target `select[data-testid="input-q_4d52c72489f0460bc3bb98fe51663e50-select"]` and select the desired option by its `value` or visible text.
- **Continue Button:** `button[data-testid="continue-button"]`