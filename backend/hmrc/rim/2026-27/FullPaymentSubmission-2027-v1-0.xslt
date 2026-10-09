<?xml version="1.0" encoding="UTF-8"?>
<axsl:stylesheet xmlns:axsl="http://www.w3.org/1999/XSL/Transform" xmlns:dsig="http://www.w3.org/2000/09/xmldsig#" xmlns:fps="http://www.govtalk.gov.uk/taxation/PAYE/RTI/FullPaymentSubmission/26-27/1" xmlns:hd="http://www.govtalk.gov.uk/CM/envelope" xmlns:date="http://exslt.org/dates-and-times" xmlns:dyn="http://exslt.org/dynamic" xmlns:exsl="http://exslt.org/common" xmlns:iso="http://purl.oclc.org/dsdl/schematron" xmlns:math="http://exslt.org/math" xmlns:random="http://exslt.org/random" xmlns:regexp="http://exslt.org/regular-expressions" xmlns:sch="http://www.ascc.net/xml/schematron" xmlns:set="http://exslt.org/sets" xmlns:str="http://exslt.org/strings" dsig:dummy-for-xmlns="" exclude-result-prefixes="sch iso" extension-element-prefixes="date dyn math random regexp set str exsl" fps:dummy-for-xmlns="" hd:dummy-for-xmlns="" version="1.0">

<!--PHASES-->


<!--PROLOG-->
<dsl-rim:namespaceMappings xmlns:dsl-rim="http://www.decisionsoft.com/rim" xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse">
    <dsl-rim:namespaceMapping prefix="hd" uri="http://www.govtalk.gov.uk/CM/envelope"/>
    <dsl-rim:namespaceMapping prefix="dsig" uri="http://www.w3.org/2000/09/xmldsig#"/>
    <dsl-rim:namespaceMapping prefix="fps" uri="http://www.govtalk.gov.uk/taxation/PAYE/RTI/FullPaymentSubmission/26-27/1"/>
  </dsl-rim:namespaceMappings>
  <axsl:output xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" indent="yes" method="xml" omit-xml-declaration="no" standalone="yes"/>

<!--KEYS-->


<!--DEFAULT RULES-->


<!--MODE: SCHEMATRON-FULL-PATH-->
<axsl:template match="*" mode="schematron-get-full-path">
    <axsl:apply-templates mode="schematron-get-full-path" select="parent::*"/>
    <axsl:text>/</axsl:text>
    <axsl:variable name="nsuri" select="namespace-uri()"/>
    <axsl:variable xmlns:dsl-rim="http://www.decisionsoft.com/rim" name="prefix" select="document('')//dsl-rim:namespaceMapping[@uri=$nsuri]/@prefix"/>
    <axsl:if test="$prefix">
      <axsl:value-of select="concat($prefix,':')"/>
    </axsl:if>
    <axsl:value-of select="local-name()"/>
    <axsl:variable name="preceding" select="count(preceding-sibling::*[local-name()=local-name(current())                                   and namespace-uri() = namespace-uri(current())])"/>
    <axsl:text>[</axsl:text>
    <axsl:value-of select="1+ $preceding"/>
    <axsl:text>]</axsl:text>
  </axsl:template>
  <axsl:template match="@*" mode="schematron-get-full-path">
    <axsl:apply-templates mode="schematron-get-full-path" select="parent::*"/>
    <axsl:text>/@</axsl:text>
    <axsl:variable name="nsuri" select="namespace-uri()"/>
    <axsl:variable xmlns:dsl-rim="http://www.decisionsoft.com/rim" name="prefix" select="document('')//dsl-rim:namespaceMapping[@uri=$nsuri]/@prefix"/>
    <axsl:if test="$prefix">
      <axsl:value-of select="concat($prefix,':')"/>
    </axsl:if>
    <axsl:value-of select="local-name()"/>
  </axsl:template>
  <!--Strip characters-->
  <axsl:template match="text()" priority="-1"/>

<!--SCHEMA METADATA-->
<axsl:template match="/">
    <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="errors">
      <axsl:apply-templates mode="M4" select="/"/>
      <axsl:apply-templates mode="M5" select="/"/>
      <axsl:apply-templates mode="M6" select="/"/>
      <axsl:apply-templates mode="M7" select="/"/>
      <axsl:apply-templates mode="M8" select="/"/>
      <axsl:apply-templates mode="M9" select="/"/>
      <axsl:apply-templates mode="M10" select="/"/>
      <axsl:apply-templates mode="M11" select="/"/>
      <axsl:apply-templates mode="M12" select="/"/>
      <axsl:apply-templates mode="M13" select="/"/>
      <axsl:apply-templates mode="M14" select="/"/>
      <axsl:apply-templates mode="M15" select="/"/>
      <axsl:apply-templates mode="M16" select="/"/>
      <axsl:apply-templates mode="M17" select="/"/>
      <axsl:apply-templates mode="M18" select="/"/>
      <axsl:apply-templates mode="M19" select="/"/>
      <axsl:apply-templates mode="M20" select="/"/>
      <axsl:apply-templates mode="M21" select="/"/>
      <axsl:apply-templates mode="M22" select="/"/>
      <axsl:apply-templates mode="M23" select="/"/>
      <axsl:apply-templates mode="M24" select="/"/>
      <axsl:apply-templates mode="M25" select="/"/>
      <axsl:apply-templates mode="M26" select="/"/>
      <axsl:apply-templates mode="M27" select="/"/>
      <axsl:apply-templates mode="M28" select="/"/>
      <axsl:apply-templates mode="M29" select="/"/>
      <axsl:apply-templates mode="M30" select="/"/>
      <axsl:apply-templates mode="M31" select="/"/>
      <axsl:apply-templates mode="M32" select="/"/>
      <axsl:apply-templates mode="M33" select="/"/>
      <axsl:apply-templates mode="M34" select="/"/>
      <axsl:apply-templates mode="M35" select="/"/>
      <axsl:apply-templates mode="M36" select="/"/>
      <axsl:apply-templates mode="M37" select="/"/>
      <axsl:apply-templates mode="M38" select="/"/>
      <axsl:apply-templates mode="M39" select="/"/>
      <axsl:apply-templates mode="M40" select="/"/>
    </axsl:variable>
    <err:ErrorResponse xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" xmlns:dsl="http://decisionsoft.com/rim/errorExtension" SchemaVersion="2.0">
      <axsl:copy-of select="$errors"/>
    </err:ErrorResponse>
  </axsl:template>

<!--SCHEMATRON PATTERNS-->


<!--PATTERN p2-->


	<!--RULE -->
<axsl:template match="/hd:GovTalkMessage/hd:Body/fps:IRenvelope/fps:IRheader/fps:Keys/fps:Key" mode="M4" priority="4000">

		<!--ASSERT -->
<axsl:choose>
      <axsl:when test="count(../../../../../hd:GovTalkDetails/hd:Keys/hd:Key[@Type = current()/@Type and . = current()]) &gt; 0"/>
      <axsl:otherwise>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="errorCode">5005</axsl:variable>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="defaultMessage">Keys in the GovTalkDetails do not match those in the IRheader.</axsl:variable>
        <err:Error xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" xmlns:dsl="http://decisionsoft.com/rim/errorExtension">
          <err:RaisedBy>ChRIS</err:RaisedBy>
          <err:Number>
            <axsl:value-of select="normalize-space($errorCode)"/>
          </err:Number>
          <err:Type>business</err:Type>
          <err:Text>
            <axsl:choose>
              <axsl:when test="normalize-space($defaultMessage)">
                <axsl:copy-of select="$defaultMessage"/>
              </axsl:when>
              <axsl:otherwise>Keys in the IR header must also exist in the GovTalk header with the same value</axsl:otherwise>
            </axsl:choose>
          </err:Text>
          <err:Location>
            <axsl:apply-templates mode="schematron-get-full-path" select="."/>
          </err:Location>
        </err:Error>
      </axsl:otherwise>
    </axsl:choose>
    <axsl:apply-templates mode="M4" select="@*|*|comment()|processing-instruction()"/>
  </axsl:template>
  <axsl:template match="text()" mode="M4" priority="-1"/>
  <axsl:template match="@*|node()" mode="M4" priority="-2">
    <axsl:apply-templates mode="M4" select="@*|node()"/>
  </axsl:template>

<!--PATTERN p1-->


	<!--RULE -->
<axsl:template match="/hd:GovTalkMessage/hd:Body/fps:IRenvelope/fps:IRheader" mode="M5" priority="4000">

		<!--ASSERT -->
<axsl:choose>
      <axsl:when test="count(fps:Keys/fps:Key) &gt; 0"/>
      <axsl:otherwise>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="errorCode">5004</axsl:variable>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="defaultMessage">At least one key must exist in the IRheader</axsl:variable>
        <err:Error xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" xmlns:dsl="http://decisionsoft.com/rim/errorExtension">
          <err:RaisedBy>ChRIS</err:RaisedBy>
          <err:Number>
            <axsl:value-of select="normalize-space($errorCode)"/>
          </err:Number>
          <err:Type>business</err:Type>
          <err:Text>
            <axsl:choose>
              <axsl:when test="normalize-space($defaultMessage)">
                <axsl:copy-of select="$defaultMessage"/>
              </axsl:when>
              <axsl:otherwise>At least one key must exist in the IRheader</axsl:otherwise>
            </axsl:choose>
          </err:Text>
          <err:Location>
            <axsl:apply-templates mode="schematron-get-full-path" select="."/>
          </err:Location>
        </err:Error>
      </axsl:otherwise>
    </axsl:choose>
    <axsl:apply-templates mode="M5" select="@*|*|comment()|processing-instruction()"/>
  </axsl:template>
  <axsl:template match="text()" mode="M5" priority="-1"/>
  <axsl:template match="@*|node()" mode="M5" priority="-2">
    <axsl:apply-templates mode="M5" select="@*|node()"/>
  </axsl:template>

<!--PATTERN p4-->


	<!--RULE -->
<axsl:template match="/hd:GovTalkMessage/hd:Body/fps:IRenvelope/fps:FullPaymentSubmission/fps:EmpRefs/fps:OfficeNo" mode="M6" priority="4000">

		<!--ASSERT -->
<axsl:choose>
      <axsl:when test="../../../fps:IRheader/fps:Keys/fps:Key[@Type = 'TaxOfficeNumber'] = ."/>
      <axsl:otherwise>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="errorCode">7821</axsl:variable>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="defaultMessage">The TaxOfficeNumber key within the IRheader must match [HMRCOFFICENUMBER]</axsl:variable>
        <err:Error xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" xmlns:dsl="http://decisionsoft.com/rim/errorExtension">
          <err:RaisedBy>ChRIS</err:RaisedBy>
          <err:Number>
            <axsl:value-of select="normalize-space($errorCode)"/>
          </err:Number>
          <err:Type>business</err:Type>
          <err:Text>
            <axsl:choose>
              <axsl:when test="normalize-space($defaultMessage)">
                <axsl:copy-of select="$defaultMessage"/>
              </axsl:when>
              <axsl:otherwise>The TaxOfficeNumber key within the IRheader must match [HMRCOFFICENUMBER]</axsl:otherwise>
            </axsl:choose>
          </err:Text>
          <err:Location>
            <axsl:apply-templates mode="schematron-get-full-path" select="."/>
          </err:Location>
        </err:Error>
      </axsl:otherwise>
    </axsl:choose>
    <axsl:apply-templates mode="M6" select="@*|*|comment()|processing-instruction()"/>
  </axsl:template>
  <axsl:template match="text()" mode="M6" priority="-1"/>
  <axsl:template match="@*|node()" mode="M6" priority="-2">
    <axsl:apply-templates mode="M6" select="@*|node()"/>
  </axsl:template>

<!--PATTERN p5-->


	<!--RULE -->
<axsl:template match="/hd:GovTalkMessage/hd:Body/fps:IRenvelope/fps:FullPaymentSubmission/fps:EmpRefs/fps:PayeRef" mode="M7" priority="4000">

		<!--ASSERT -->
<axsl:choose>
      <axsl:when test="../../../fps:IRheader/fps:Keys/fps:Key[@Type = 'TaxOfficeReference'] = ."/>
      <axsl:otherwise>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="errorCode">7822</axsl:variable>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="defaultMessage">The TaxOfficeReference key within the IRheader must match [EMPLOYERPAYEREF]</axsl:variable>
        <err:Error xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" xmlns:dsl="http://decisionsoft.com/rim/errorExtension">
          <err:RaisedBy>ChRIS</err:RaisedBy>
          <err:Number>
            <axsl:value-of select="normalize-space($errorCode)"/>
          </err:Number>
          <err:Type>business</err:Type>
          <err:Text>
            <axsl:choose>
              <axsl:when test="normalize-space($defaultMessage)">
                <axsl:copy-of select="$defaultMessage"/>
              </axsl:when>
              <axsl:otherwise>The TaxOfficeReference key within the IRheader must match [EMPLOYERPAYEREF]</axsl:otherwise>
            </axsl:choose>
          </err:Text>
          <err:Location>
            <axsl:apply-templates mode="schematron-get-full-path" select="."/>
          </err:Location>
        </err:Error>
      </axsl:otherwise>
    </axsl:choose>
    <axsl:apply-templates mode="M7" select="@*|*|comment()|processing-instruction()"/>
  </axsl:template>
  <axsl:template match="text()" mode="M7" priority="-1"/>
  <axsl:template match="@*|node()" mode="M7" priority="-2">
    <axsl:apply-templates mode="M7" select="@*|node()"/>
  </axsl:template>

<!--PATTERN p6-->


	<!--RULE -->
<axsl:template match="/hd:GovTalkMessage/hd:Body/fps:IRenvelope/fps:FullPaymentSubmission/fps:EmpRefs/fps:SAUTR" mode="M8" priority="4000">

		<!--ASSERT -->
<axsl:choose>
      <axsl:when test="(((11 - (((6 * substring(., 2, 1)) + (7 * substring(., 3, 1)) + (8 * substring(., 4, 1)) + (9 * substring(., 5, 1)) + (10 * substring(., 6, 1)) + (5 * substring(., 7, 1)) + (4 * substring(., 8, 1)) + (3 * substring(., 9, 1)) + (2 * substring(., 10, 1))) mod 11)) &gt; 9) and (substring(., 1, 1) = (11 - (((6 * substring(., 2, 1)) + (7 * substring(., 3, 1)) + (8 * substring(., 4, 1)) + (9 * substring(., 5, 1)) + (10 * substring(., 6, 1)) + (5 * substring(., 7, 1)) + (4 * substring(., 8, 1)) + (3 * substring(., 9, 1)) + (2 * substring(., 10, 1))) mod 11)) - 9))                 or                 (substring(., 1, 1) = (11 - (((6 * substring(., 2, 1)) + (7 * substring(., 3, 1)) + (8 * substring(., 4, 1)) + (9 * substring(., 5, 1)) + (10 * substring(., 6, 1)) + (5 * substring(., 7, 1)) + (4 * substring(., 8, 1)) + (3 * substring(., 9, 1)) + (2 * substring(., 10, 1))) mod 11)))"/>
      <axsl:otherwise>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="errorCode">7882</axsl:variable>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="defaultMessage">The entry must be a valid UTR. Please check.</axsl:variable>
        <err:Error xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" xmlns:dsl="http://decisionsoft.com/rim/errorExtension">
          <err:RaisedBy>ChRIS</err:RaisedBy>
          <err:Number>
            <axsl:value-of select="normalize-space($errorCode)"/>
          </err:Number>
          <err:Type>business</err:Type>
          <err:Text>
            <axsl:choose>
              <axsl:when test="normalize-space($defaultMessage)">
                <axsl:copy-of select="$defaultMessage"/>
              </axsl:when>
              <axsl:otherwise>Must be valid against the UTR algorithm</axsl:otherwise>
            </axsl:choose>
          </err:Text>
          <err:Location>
            <axsl:apply-templates mode="schematron-get-full-path" select="."/>
          </err:Location>
        </err:Error>
      </axsl:otherwise>
    </axsl:choose>

		<!--ASSERT -->
<axsl:choose>
      <axsl:when test="not(../fps:COTAXRef)"/>
      <axsl:otherwise>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="errorCode">7952</axsl:variable>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="defaultMessage">If [SAUTR] is present [COTAXREF] must be absent</axsl:variable>
        <err:Error xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" xmlns:dsl="http://decisionsoft.com/rim/errorExtension">
          <err:RaisedBy>ChRIS</err:RaisedBy>
          <err:Number>
            <axsl:value-of select="normalize-space($errorCode)"/>
          </err:Number>
          <err:Type>business</err:Type>
          <err:Text>
            <axsl:choose>
              <axsl:when test="normalize-space($defaultMessage)">
                <axsl:copy-of select="$defaultMessage"/>
              </axsl:when>
              <axsl:otherwise>If [SAUTR] is present [COTAXREF] must be absent</axsl:otherwise>
            </axsl:choose>
          </err:Text>
          <err:Location>
            <axsl:apply-templates mode="schematron-get-full-path" select="."/>
          </err:Location>
        </err:Error>
      </axsl:otherwise>
    </axsl:choose>
    <axsl:apply-templates mode="M8" select="@*|*|comment()|processing-instruction()"/>
  </axsl:template>
  <axsl:template match="text()" mode="M8" priority="-1"/>
  <axsl:template match="@*|node()" mode="M8" priority="-2">
    <axsl:apply-templates mode="M8" select="@*|node()"/>
  </axsl:template>

<!--PATTERN p7-->


	<!--RULE -->
<axsl:template match="/hd:GovTalkMessage/hd:Body/fps:IRenvelope/fps:FullPaymentSubmission/fps:EmpRefs/fps:COTAXRef" mode="M9" priority="4000">

		<!--ASSERT -->
<axsl:choose>
      <axsl:when test="(((11 - (((6 * substring(., 2, 1)) + (7 * substring(., 3, 1)) + (8 * substring(., 4, 1)) + (9 * substring(., 5, 1)) + (10 * substring(., 6, 1)) + (5 * substring(., 7, 1)) + (4 * substring(., 8, 1)) + (3 * substring(., 9, 1)) + (2 * substring(., 10, 1))) mod 11)) &gt; 9) and (substring(., 1, 1) = (11 - (((6 * substring(., 2, 1)) + (7 * substring(., 3, 1)) + (8 * substring(., 4, 1)) + (9 * substring(., 5, 1)) + (10 * substring(., 6, 1)) + (5 * substring(., 7, 1)) + (4 * substring(., 8, 1)) + (3 * substring(., 9, 1)) + (2 * substring(., 10, 1))) mod 11)) - 9))                 or                 (substring(., 1, 1) = (11 - (((6 * substring(., 2, 1)) + (7 * substring(., 3, 1)) + (8 * substring(., 4, 1)) + (9 * substring(., 5, 1)) + (10 * substring(., 6, 1)) + (5 * substring(., 7, 1)) + (4 * substring(., 8, 1)) + (3 * substring(., 9, 1)) + (2 * substring(., 10, 1))) mod 11)))"/>
      <axsl:otherwise>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="errorCode">7882</axsl:variable>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="defaultMessage">The entry must be a valid UTR. Please check.</axsl:variable>
        <err:Error xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" xmlns:dsl="http://decisionsoft.com/rim/errorExtension">
          <err:RaisedBy>ChRIS</err:RaisedBy>
          <err:Number>
            <axsl:value-of select="normalize-space($errorCode)"/>
          </err:Number>
          <err:Type>business</err:Type>
          <err:Text>
            <axsl:choose>
              <axsl:when test="normalize-space($defaultMessage)">
                <axsl:copy-of select="$defaultMessage"/>
              </axsl:when>
              <axsl:otherwise>Must be valid against the UTR algorithm</axsl:otherwise>
            </axsl:choose>
          </err:Text>
          <err:Location>
            <axsl:apply-templates mode="schematron-get-full-path" select="."/>
          </err:Location>
        </err:Error>
      </axsl:otherwise>
    </axsl:choose>
    <axsl:apply-templates mode="M9" select="@*|*|comment()|processing-instruction()"/>
  </axsl:template>
  <axsl:template match="text()" mode="M9" priority="-1"/>
  <axsl:template match="@*|node()" mode="M9" priority="-2">
    <axsl:apply-templates mode="M9" select="@*|node()"/>
  </axsl:template>

<!--PATTERN p8-->


	<!--RULE -->
<axsl:template match="/hd:GovTalkMessage/hd:Body/fps:IRenvelope/fps:FullPaymentSubmission/fps:RelatedTaxYear" mode="M10" priority="4000">

		<!--ASSERT -->
<axsl:choose>
      <axsl:when test="substring(string(2027 - 1), 3, 2) = substring(., 1, 2)           and             substring(2027, 3, 2) = substring(., 4, 2)"/>
      <axsl:otherwise>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="errorCode">7889</axsl:variable>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="defaultMessage">The Related tax year entered is invalid. Please check</axsl:variable>
        <err:Error xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" xmlns:dsl="http://decisionsoft.com/rim/errorExtension">
          <err:RaisedBy>ChRIS</err:RaisedBy>
          <err:Number>
            <axsl:value-of select="normalize-space($errorCode)"/>
          </err:Number>
          <err:Type>business</err:Type>
          <err:Text>
            <axsl:choose>
              <axsl:when test="normalize-space($defaultMessage)">
                <axsl:copy-of select="$defaultMessage"/>
              </axsl:when>
              <axsl:otherwise>Must be the appropriate tax year for the schema year. I.E. 26-27 for RTI-2027</axsl:otherwise>
            </axsl:choose>
          </err:Text>
          <err:Location>
            <axsl:apply-templates mode="schematron-get-full-path" select="."/>
          </err:Location>
        </err:Error>
      </axsl:otherwise>
    </axsl:choose>

		<!--ASSERT -->
<axsl:choose>
      <axsl:when test="(round(date:seconds(normalize-space(concat(2000 + number(substring(.,1,2)), '-04-06'))) div 86400) &lt;= round(date:seconds(normalize-space(../../fps:IRheader/fps:PeriodEnd)) div 86400))         and           (round(date:seconds(normalize-space(../../fps:IRheader/fps:PeriodEnd)) div 86400) &lt;= round(date:seconds(normalize-space(concat(2001 + number(substring(.,1,2)), '-04-05'))) div 86400))"/>
      <axsl:otherwise>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="errorCode">7844</axsl:variable>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="defaultMessage">The PeriodEnd within the IRheader must be within the same tax year as [RELATEDTAXYEAR].</axsl:variable>
        <err:Error xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" xmlns:dsl="http://decisionsoft.com/rim/errorExtension">
          <err:RaisedBy>ChRIS</err:RaisedBy>
          <err:Number>
            <axsl:value-of select="normalize-space($errorCode)"/>
          </err:Number>
          <err:Type>business</err:Type>
          <err:Text>
            <axsl:choose>
              <axsl:when test="normalize-space($defaultMessage)">
                <axsl:copy-of select="$defaultMessage"/>
              </axsl:when>
              <axsl:otherwise>The PeriodEnd within the IRheader must be within the same tax year as [RELATEDTAXYEAR].</axsl:otherwise>
            </axsl:choose>
          </err:Text>
          <err:Location>
            <axsl:apply-templates mode="schematron-get-full-path" select="."/>
          </err:Location>
        </err:Error>
      </axsl:otherwise>
    </axsl:choose>
    <axsl:apply-templates mode="M10" select="@*|*|comment()|processing-instruction()"/>
  </axsl:template>
  <axsl:template match="text()" mode="M10" priority="-1"/>
  <axsl:template match="@*|node()" mode="M10" priority="-2">
    <axsl:apply-templates mode="M10" select="@*|node()"/>
  </axsl:template>

<!--PATTERN p11-->


	<!--RULE -->
<axsl:template match="/hd:GovTalkMessage/hd:Body/fps:IRenvelope/fps:FullPaymentSubmission/fps:Employee/fps:EmployeeDetails/fps:Address/fps:ForeignCountry" mode="M11" priority="4000">

		<!--ASSERT -->
<axsl:choose>
      <axsl:when test="(count(../fps:Line)) &gt;= 2"/>
      <axsl:otherwise>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="errorCode">7825</axsl:variable>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="defaultMessage">There is an entry in [FOREIGNCOUNTRY]. Please complete at least two [ADDRESSLINE] </axsl:variable>
        <err:Error xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" xmlns:dsl="http://decisionsoft.com/rim/errorExtension">
          <err:RaisedBy>ChRIS</err:RaisedBy>
          <err:Number>
            <axsl:value-of select="normalize-space($errorCode)"/>
          </err:Number>
          <err:Type>business</err:Type>
          <err:Text>
            <axsl:choose>
              <axsl:when test="normalize-space($defaultMessage)">
                <axsl:copy-of select="$defaultMessage"/>
              </axsl:when>
              <axsl:otherwise>If [FOREIGNCOUNTRY] is present, at least two [ADDRESSLINE] should be present</axsl:otherwise>
            </axsl:choose>
          </err:Text>
          <err:Location>
            <axsl:apply-templates mode="schematron-get-full-path" select="."/>
          </err:Location>
        </err:Error>
      </axsl:otherwise>
    </axsl:choose>
    <axsl:apply-templates mode="M11" select="@*|*|comment()|processing-instruction()"/>
  </axsl:template>
  <axsl:template match="text()" mode="M11" priority="-1"/>
  <axsl:template match="@*|node()" mode="M11" priority="-2">
    <axsl:apply-templates mode="M11" select="@*|node()"/>
  </axsl:template>

<!--PATTERN p12-->


	<!--RULE -->
<axsl:template match="/hd:GovTalkMessage/hd:Body/fps:IRenvelope/fps:FullPaymentSubmission/fps:Employee/fps:EmployeeDetails/fps:BirthDate" mode="M12" priority="4000">

		<!--ASSERT -->
<axsl:choose>
      <axsl:when test="(round(date:seconds(normalize-space((.))) div 86400) &lt;= round(date:seconds(normalize-space(date:date())) div 86400))"/>
      <axsl:otherwise>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="errorCode">5001</axsl:variable>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="defaultMessage">The Date must be today or earlier. Please check</axsl:variable>
        <err:Error xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" xmlns:dsl="http://decisionsoft.com/rim/errorExtension">
          <err:RaisedBy>ChRIS</err:RaisedBy>
          <err:Number>
            <axsl:value-of select="normalize-space($errorCode)"/>
          </err:Number>
          <err:Type>business</err:Type>
          <err:Text>
            <axsl:choose>
              <axsl:when test="normalize-space($defaultMessage)">
                <axsl:copy-of select="$defaultMessage"/>
              </axsl:when>
              <axsl:otherwise>The Date of Birth must be today or earlier.</axsl:otherwise>
            </axsl:choose>
          </err:Text>
          <err:Location>
            <axsl:apply-templates mode="schematron-get-full-path" select="."/>
          </err:Location>
        </err:Error>
      </axsl:otherwise>
    </axsl:choose>

		<!--ASSERT -->
<axsl:choose>
      <axsl:when test="(round(date:seconds(normalize-space(date:add(normalize-space(date:date()),normalize-space(&quot;-P130Y&quot;)))) div 86400) &lt; round(date:seconds(normalize-space((.))) div 86400))"/>
      <axsl:otherwise>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="errorCode">7826</axsl:variable>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="defaultMessage">[DATEOFBIRTH] must be later than 130 years before today's date. Please check </axsl:variable>
        <err:Error xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" xmlns:dsl="http://decisionsoft.com/rim/errorExtension">
          <err:RaisedBy>ChRIS</err:RaisedBy>
          <err:Number>
            <axsl:value-of select="normalize-space($errorCode)"/>
          </err:Number>
          <err:Type>business</err:Type>
          <err:Text>
            <axsl:choose>
              <axsl:when test="normalize-space($defaultMessage)">
                <axsl:copy-of select="$defaultMessage"/>
              </axsl:when>
              <axsl:otherwise>Must be later than 130 years before today</axsl:otherwise>
            </axsl:choose>
          </err:Text>
          <err:Location>
            <axsl:apply-templates mode="schematron-get-full-path" select="."/>
          </err:Location>
        </err:Error>
      </axsl:otherwise>
    </axsl:choose>
    <axsl:apply-templates mode="M12" select="@*|*|comment()|processing-instruction()"/>
  </axsl:template>
  <axsl:template match="text()" mode="M12" priority="-1"/>
  <axsl:template match="@*|node()" mode="M12" priority="-2">
    <axsl:apply-templates mode="M12" select="@*|node()"/>
  </axsl:template>

<!--PATTERN p13-->


	<!--RULE -->
<axsl:template match="/hd:GovTalkMessage/hd:Body/fps:IRenvelope/fps:FullPaymentSubmission/fps:Employee/fps:EmployeeDetails/fps:PartnerDetails" mode="M13" priority="4000">

		<!--ASSERT -->
<axsl:choose>
      <axsl:when test="(fps:Name/fps:Initials or fps:Name/fps:Fore)"/>
      <axsl:otherwise>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="errorCode">7846</axsl:variable>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="defaultMessage">There must be an entry in [PARTNERFORENAME] or [PARTNERINITIALS] if [PARTNERDETAILS] is submitted. Please check</axsl:variable>
        <err:Error xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" xmlns:dsl="http://decisionsoft.com/rim/errorExtension">
          <err:RaisedBy>ChRIS</err:RaisedBy>
          <err:Number>
            <axsl:value-of select="normalize-space($errorCode)"/>
          </err:Number>
          <err:Type>business</err:Type>
          <err:Text>
            <axsl:choose>
              <axsl:when test="normalize-space($defaultMessage)">
                <axsl:copy-of select="$defaultMessage"/>
              </axsl:when>
              <axsl:otherwise>[PARTNERFORENAME] should be present if [PARTNERINITIALS] is absent</axsl:otherwise>
            </axsl:choose>
          </err:Text>
          <err:Location>
            <axsl:apply-templates mode="schematron-get-full-path" select="."/>
          </err:Location>
        </err:Error>
      </axsl:otherwise>
    </axsl:choose>
    <axsl:apply-templates mode="M13" select="@*|*|comment()|processing-instruction()"/>
  </axsl:template>
  <axsl:template match="text()" mode="M13" priority="-1"/>
  <axsl:template match="@*|node()" mode="M13" priority="-2">
    <axsl:apply-templates mode="M13" select="@*|node()"/>
  </axsl:template>

<!--PATTERN p10-->


	<!--RULE -->
<axsl:template match="/hd:GovTalkMessage/hd:Body/fps:IRenvelope/fps:FullPaymentSubmission/fps:Employee/fps:EmployeeDetails" mode="M14" priority="4000">

		<!--ASSERT -->
<axsl:choose>
      <axsl:when test="fps:NINO             or               count(fps:Address/fps:Line) &gt;= 2"/>
      <axsl:otherwise>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="errorCode">7823</axsl:variable>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="defaultMessage">There is no entry in [NINO]. Please complete at least two [ADDRESSLINE] </axsl:variable>
        <err:Error xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" xmlns:dsl="http://decisionsoft.com/rim/errorExtension">
          <err:RaisedBy>ChRIS</err:RaisedBy>
          <err:Number>
            <axsl:value-of select="normalize-space($errorCode)"/>
          </err:Number>
          <err:Type>business</err:Type>
          <err:Text>
            <axsl:choose>
              <axsl:when test="normalize-space($defaultMessage)">
                <axsl:copy-of select="$defaultMessage"/>
              </axsl:when>
              <axsl:otherwise>At least two [ADDRESSLINE] should be present if not ( [NINO] is present )</axsl:otherwise>
            </axsl:choose>
          </err:Text>
          <err:Location>
            <axsl:apply-templates mode="schematron-get-full-path" select="."/>
          </err:Location>
        </err:Error>
      </axsl:otherwise>
    </axsl:choose>

		<!--ASSERT -->
<axsl:choose>
      <axsl:when test="fps:Name/fps:Fore or fps:Name/fps:Initials"/>
      <axsl:otherwise>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="errorCode">7824</axsl:variable>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="defaultMessage">There must be an entry in either [FORENAME] or [INITIALS]</axsl:variable>
        <err:Error xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" xmlns:dsl="http://decisionsoft.com/rim/errorExtension">
          <err:RaisedBy>ChRIS</err:RaisedBy>
          <err:Number>
            <axsl:value-of select="normalize-space($errorCode)"/>
          </err:Number>
          <err:Type>business</err:Type>
          <err:Text>
            <axsl:choose>
              <axsl:when test="normalize-space($defaultMessage)">
                <axsl:copy-of select="$defaultMessage"/>
              </axsl:when>
              <axsl:otherwise>At least one of [FORENAME] and [INITIALS] must be present</axsl:otherwise>
            </axsl:choose>
          </err:Text>
          <err:Location>
            <axsl:apply-templates mode="schematron-get-full-path" select="."/>
          </err:Location>
        </err:Error>
      </axsl:otherwise>
    </axsl:choose>
    <axsl:apply-templates mode="M14" select="@*|*|comment()|processing-instruction()"/>
  </axsl:template>
  <axsl:template match="text()" mode="M14" priority="-1"/>
  <axsl:template match="@*|node()" mode="M14" priority="-2">
    <axsl:apply-templates mode="M14" select="@*|node()"/>
  </axsl:template>

<!--PATTERN p15-->


	<!--RULE -->
<axsl:template match="/hd:GovTalkMessage/hd:Body/fps:IRenvelope/fps:FullPaymentSubmission/fps:Employee/fps:Employment/fps:TaxWkOfApptOfDirector" mode="M15" priority="4000">

		<!--ASSERT -->
<axsl:choose>
      <axsl:when test="../fps:DirectorsNIC"/>
      <axsl:otherwise>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="errorCode">7883</axsl:variable>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="defaultMessage">If [TAXWKOFAPPTOFDIRECTOR] is entered then [DIRECTORSNIC] must be completed. Please check</axsl:variable>
        <err:Error xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" xmlns:dsl="http://decisionsoft.com/rim/errorExtension">
          <err:RaisedBy>ChRIS</err:RaisedBy>
          <err:Number>
            <axsl:value-of select="normalize-space($errorCode)"/>
          </err:Number>
          <err:Type>business</err:Type>
          <err:Text>
            <axsl:choose>
              <axsl:when test="normalize-space($defaultMessage)">
                <axsl:copy-of select="$defaultMessage"/>
              </axsl:when>
              <axsl:otherwise>If [TAXWKOFAPPTOFDIRECTOR] is present then [DIRECTORSNIC] must be present</axsl:otherwise>
            </axsl:choose>
          </err:Text>
          <err:Location>
            <axsl:apply-templates mode="schematron-get-full-path" select="."/>
          </err:Location>
        </err:Error>
      </axsl:otherwise>
    </axsl:choose>
    <axsl:apply-templates mode="M15" select="@*|*|comment()|processing-instruction()"/>
  </axsl:template>
  <axsl:template match="text()" mode="M15" priority="-1"/>
  <axsl:template match="@*|node()" mode="M15" priority="-2">
    <axsl:apply-templates mode="M15" select="@*|node()"/>
  </axsl:template>

<!--PATTERN p16-->


	<!--RULE -->
<axsl:template match="/hd:GovTalkMessage/hd:Body/fps:IRenvelope/fps:FullPaymentSubmission/fps:Employee/fps:Employment/fps:Starter/fps:StartDate" mode="M16" priority="4000">

		<!--ASSERT -->
<axsl:choose>
      <axsl:when test="(round(date:seconds(normalize-space(.)) div 86400) &lt;= round(date:seconds(normalize-space(date:add(normalize-space(date:date()),normalize-space(&quot;P30D&quot;)))) div 86400))"/>
      <axsl:otherwise>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="errorCode">7828</axsl:variable>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="defaultMessage">The [STARTDATE] must be a date in the past or any date from today to 30 days in the future. Please check</axsl:variable>
        <err:Error xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" xmlns:dsl="http://decisionsoft.com/rim/errorExtension">
          <err:RaisedBy>ChRIS</err:RaisedBy>
          <err:Number>
            <axsl:value-of select="normalize-space($errorCode)"/>
          </err:Number>
          <err:Type>business</err:Type>
          <err:Text>
            <axsl:choose>
              <axsl:when test="normalize-space($defaultMessage)">
                <axsl:copy-of select="$defaultMessage"/>
              </axsl:when>
              <axsl:otherwise>[STARTDATE] must be no later than current date plus 30 days (i.e. Also any date in the past allowed)</axsl:otherwise>
            </axsl:choose>
          </err:Text>
          <err:Location>
            <axsl:apply-templates mode="schematron-get-full-path" select="."/>
          </err:Location>
        </err:Error>
      </axsl:otherwise>
    </axsl:choose>

		<!--ASSERT -->
<axsl:choose>
      <axsl:when test="not((.))           or             (count(../../../fps:EmployeeDetails/fps:Address/fps:Line)) &gt;= 2"/>
      <axsl:otherwise>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="errorCode">7829</axsl:variable>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="defaultMessage">There is an entry in [STARTDATE]. Please complete at least two [ADDRESSLINE]s</axsl:variable>
        <err:Error xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" xmlns:dsl="http://decisionsoft.com/rim/errorExtension">
          <err:RaisedBy>ChRIS</err:RaisedBy>
          <err:Number>
            <axsl:value-of select="normalize-space($errorCode)"/>
          </err:Number>
          <err:Type>business</err:Type>
          <err:Text>
            <axsl:choose>
              <axsl:when test="normalize-space($defaultMessage)">
                <axsl:copy-of select="$defaultMessage"/>
              </axsl:when>
              <axsl:otherwise>At least two [ADDRESSLINE]s should be present if [STARTDATE] is present</axsl:otherwise>
            </axsl:choose>
          </err:Text>
          <err:Location>
            <axsl:apply-templates mode="schematron-get-full-path" select="."/>
          </err:Location>
        </err:Error>
      </axsl:otherwise>
    </axsl:choose>
    <axsl:apply-templates mode="M16" select="@*|*|comment()|processing-instruction()"/>
  </axsl:template>
  <axsl:template match="text()" mode="M16" priority="-1"/>
  <axsl:template match="@*|node()" mode="M16" priority="-2">
    <axsl:apply-templates mode="M16" select="@*|node()"/>
  </axsl:template>

<!--PATTERN p18-->


	<!--RULE -->
<axsl:template match="/hd:GovTalkMessage/hd:Body/fps:IRenvelope/fps:FullPaymentSubmission/fps:Employee/fps:Employment/fps:Starter/fps:Seconded/fps:EEACitizen" mode="M17" priority="4000">

		<!--ASSERT -->
<axsl:choose>
      <axsl:when test="../fps:StayLessThan183Days             or           ../fps:Stay183DaysOrMore             or           ../fps:InOutUK"/>
      <axsl:otherwise>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="errorCode">7884</axsl:variable>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="defaultMessage">If [EEACITIZEN] is selected you must also select one of [INTENDTOSTAYLESSTHAN183DAYS],[INTENDTOSTAYOVER183DAYS] or [INTENDTOWORKBOTHINANDOUTOFUK]</axsl:variable>
        <err:Error xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" xmlns:dsl="http://decisionsoft.com/rim/errorExtension">
          <err:RaisedBy>ChRIS</err:RaisedBy>
          <err:Number>
            <axsl:value-of select="normalize-space($errorCode)"/>
          </err:Number>
          <err:Type>business</err:Type>
          <err:Text>
            <axsl:choose>
              <axsl:when test="normalize-space($defaultMessage)">
                <axsl:copy-of select="$defaultMessage"/>
              </axsl:when>
              <axsl:otherwise>If [EEACITIZEN] is present the following should be true: [INTENDTOSTAYLESSTHAN183DAYS] is present or [INTENDTOSTAYOVER183DAYS] is present or [INTENDTOWORKBOTHINANDOUTOFUK] is present</axsl:otherwise>
            </axsl:choose>
          </err:Text>
          <err:Location>
            <axsl:apply-templates mode="schematron-get-full-path" select="."/>
          </err:Location>
        </err:Error>
      </axsl:otherwise>
    </axsl:choose>
    <axsl:apply-templates mode="M17" select="@*|*|comment()|processing-instruction()"/>
  </axsl:template>
  <axsl:template match="text()" mode="M17" priority="-1"/>
  <axsl:template match="@*|node()" mode="M17" priority="-2">
    <axsl:apply-templates mode="M17" select="@*|node()"/>
  </axsl:template>

<!--PATTERN p17-->


	<!--RULE -->
<axsl:template match="/hd:GovTalkMessage/hd:Body/fps:IRenvelope/fps:FullPaymentSubmission/fps:Employee/fps:Employment/fps:Starter/fps:Seconded" mode="M18" priority="4000">

		<!--ASSERT -->
<axsl:choose>
      <axsl:when test="fps:Stay183DaysOrMore or fps:StayLessThan183Days or fps:InOutUK or fps:EPM6"/>
      <axsl:otherwise>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="errorCode">7931</axsl:variable>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="defaultMessage"> If [INDIVIDUALSECONDEDTOWORKINUK] is present, at least one of [INTENDTOSTAYOVER183DAYS], [INTENDTOSTAYLESSTHAN183DAYS], [INTENDTOWORKBOTHINANDOUTOFUK] or [EPM6SCHEME] must be present. Please check.</axsl:variable>
        <err:Error xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" xmlns:dsl="http://decisionsoft.com/rim/errorExtension">
          <err:RaisedBy>ChRIS</err:RaisedBy>
          <err:Number>
            <axsl:value-of select="normalize-space($errorCode)"/>
          </err:Number>
          <err:Type>business</err:Type>
          <err:Text>
            <axsl:choose>
              <axsl:when test="normalize-space($defaultMessage)">
                <axsl:copy-of select="$defaultMessage"/>
              </axsl:when>
              <axsl:otherwise> If [INDIVIDUALSECONDEDTOWORKINUK] is present, at least one of [INTENDTOSTAYOVER183DAYS], [INTENDTOSTAYLESSTHAN183DAYS], [INTENDTOWORKBOTHINANDOUTOFUK] or [EPM6SCHEME] should be present </axsl:otherwise>
            </axsl:choose>
          </err:Text>
          <err:Location>
            <axsl:apply-templates mode="schematron-get-full-path" select="."/>
          </err:Location>
        </err:Error>
      </axsl:otherwise>
    </axsl:choose>
    <axsl:apply-templates mode="M18" select="@*|*|comment()|processing-instruction()"/>
  </axsl:template>
  <axsl:template match="text()" mode="M18" priority="-1"/>
  <axsl:template match="@*|node()" mode="M18" priority="-2">
    <axsl:apply-templates mode="M18" select="@*|node()"/>
  </axsl:template>

<!--PATTERN p19-->


	<!--RULE -->
<axsl:template match="/hd:GovTalkMessage/hd:Body/fps:IRenvelope/fps:FullPaymentSubmission/fps:Employee/fps:Employment/fps:LeavingDate" mode="M19" priority="4000">

		<!--ASSERT -->
<axsl:choose>
      <axsl:when test="(round(date:seconds(normalize-space(.)) div 86400) &lt;= round(date:seconds(normalize-space(date:add(normalize-space(date:date()),normalize-space('P30D')))) div 86400))"/>
      <axsl:otherwise>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="errorCode">7831</axsl:variable>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="defaultMessage">The [LEAVINGDATE] cannot be a future date more than thirty days from today. Please check</axsl:variable>
        <err:Error xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" xmlns:dsl="http://decisionsoft.com/rim/errorExtension">
          <err:RaisedBy>ChRIS</err:RaisedBy>
          <err:Number>
            <axsl:value-of select="normalize-space($errorCode)"/>
          </err:Number>
          <err:Type>business</err:Type>
          <err:Text>
            <axsl:choose>
              <axsl:when test="normalize-space($defaultMessage)">
                <axsl:copy-of select="$defaultMessage"/>
              </axsl:when>
              <axsl:otherwise>[LEAVINGDATE] must not be later than thirty days after today</axsl:otherwise>
            </axsl:choose>
          </err:Text>
          <err:Location>
            <axsl:apply-templates mode="schematron-get-full-path" select="."/>
          </err:Location>
        </err:Error>
      </axsl:otherwise>
    </axsl:choose>
    <axsl:apply-templates mode="M19" select="@*|*|comment()|processing-instruction()"/>
  </axsl:template>
  <axsl:template match="text()" mode="M19" priority="-1"/>
  <axsl:template match="@*|node()" mode="M19" priority="-2">
    <axsl:apply-templates mode="M19" select="@*|node()"/>
  </axsl:template>

<!--PATTERN p20-->


	<!--RULE -->
<axsl:template match="/hd:GovTalkMessage/hd:Body/fps:IRenvelope/fps:FullPaymentSubmission/fps:Employee/fps:Employment/fps:Payment/fps:PmtAfterLeaving" mode="M20" priority="4000">

		<!--ASSERT -->
<axsl:choose>
      <axsl:when test="../../fps:LeavingDate"/>
      <axsl:otherwise>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="errorCode">7847</axsl:variable>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="defaultMessage">The [PAYMENTAFTERLEAVINGDATEINDICATOR] is set. Please complete [LEAVINGDATE] </axsl:variable>
        <err:Error xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" xmlns:dsl="http://decisionsoft.com/rim/errorExtension">
          <err:RaisedBy>ChRIS</err:RaisedBy>
          <err:Number>
            <axsl:value-of select="normalize-space($errorCode)"/>
          </err:Number>
          <err:Type>business</err:Type>
          <err:Text>
            <axsl:choose>
              <axsl:when test="normalize-space($defaultMessage)">
                <axsl:copy-of select="$defaultMessage"/>
              </axsl:when>
              <axsl:otherwise>If [PAYMENTAFTERLEAVINGDATEINDICATOR] is present the following should be true: [LEAVINGDATE] is present</axsl:otherwise>
            </axsl:choose>
          </err:Text>
          <err:Location>
            <axsl:apply-templates mode="schematron-get-full-path" select="."/>
          </err:Location>
        </err:Error>
      </axsl:otherwise>
    </axsl:choose>
    <axsl:apply-templates mode="M20" select="@*|*|comment()|processing-instruction()"/>
  </axsl:template>
  <axsl:template match="text()" mode="M20" priority="-1"/>
  <axsl:template match="@*|node()" mode="M20" priority="-2">
    <axsl:apply-templates mode="M20" select="@*|node()"/>
  </axsl:template>

<!--PATTERN p21-->


	<!--RULE -->
<axsl:template match="/hd:GovTalkMessage/hd:Body/fps:IRenvelope/fps:FullPaymentSubmission/fps:Employee/fps:Employment/fps:Payment/fps:Benefits/fps:Car/fps:FirstRegd" mode="M21" priority="4000">

		<!--ASSERT -->
<axsl:choose>
      <axsl:when test="(round(date:seconds(normalize-space(.)) div 86400) &lt;= round(date:seconds(normalize-space(date:date())) div 86400))"/>
      <axsl:otherwise>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="errorCode">7939</axsl:variable>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="defaultMessage">[DATEFIRSTREGISTERED] must be today or earlier. Please check</axsl:variable>
        <err:Error xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" xmlns:dsl="http://decisionsoft.com/rim/errorExtension">
          <err:RaisedBy>ChRIS</err:RaisedBy>
          <err:Number>
            <axsl:value-of select="normalize-space($errorCode)"/>
          </err:Number>
          <err:Type>business</err:Type>
          <err:Text>
            <axsl:choose>
              <axsl:when test="normalize-space($defaultMessage)">
                <axsl:copy-of select="$defaultMessage"/>
              </axsl:when>
              <axsl:otherwise>[DATEFIRSTREGISTERED] must be today or earlier.</axsl:otherwise>
            </axsl:choose>
          </err:Text>
          <err:Location>
            <axsl:apply-templates mode="schematron-get-full-path" select="."/>
          </err:Location>
        </err:Error>
      </axsl:otherwise>
    </axsl:choose>
    <axsl:apply-templates mode="M21" select="@*|*|comment()|processing-instruction()"/>
  </axsl:template>
  <axsl:template match="text()" mode="M21" priority="-1"/>
  <axsl:template match="@*|node()" mode="M21" priority="-2">
    <axsl:apply-templates mode="M21" select="@*|node()"/>
  </axsl:template>

<!--PATTERN p22-->


	<!--RULE -->
<axsl:template match="/hd:GovTalkMessage/hd:Body/fps:IRenvelope/fps:FullPaymentSubmission/fps:Employee/fps:Employment/fps:Payment/fps:Benefits/fps:Car/fps:AvailTo" mode="M22" priority="4000">

		<!--ASSERT -->
<axsl:choose>
      <axsl:when test="(round(date:seconds(normalize-space(../fps:AvailFrom)) div 86400) &lt;= round(date:seconds(normalize-space((.))) div 86400))"/>
      <axsl:otherwise>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="errorCode">7937</axsl:variable>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="defaultMessage">[CARAVAILABLETO] must not be before [CARAVAILABLEFROM]. Please check</axsl:variable>
        <err:Error xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" xmlns:dsl="http://decisionsoft.com/rim/errorExtension">
          <err:RaisedBy>ChRIS</err:RaisedBy>
          <err:Number>
            <axsl:value-of select="normalize-space($errorCode)"/>
          </err:Number>
          <err:Type>business</err:Type>
          <err:Text>
            <axsl:choose>
              <axsl:when test="normalize-space($defaultMessage)">
                <axsl:copy-of select="$defaultMessage"/>
              </axsl:when>
              <axsl:otherwise>[CARAVAILABLETO] must not be before [CARAVAILABLEFROM]</axsl:otherwise>
            </axsl:choose>
          </err:Text>
          <err:Location>
            <axsl:apply-templates mode="schematron-get-full-path" select="."/>
          </err:Location>
        </err:Error>
      </axsl:otherwise>
    </axsl:choose>
    <axsl:apply-templates mode="M22" select="@*|*|comment()|processing-instruction()"/>
  </axsl:template>
  <axsl:template match="text()" mode="M22" priority="-1"/>
  <axsl:template match="@*|node()" mode="M22" priority="-2">
    <axsl:apply-templates mode="M22" select="@*|node()"/>
  </axsl:template>

<!--PATTERN p23-->


	<!--RULE -->
<axsl:template match="/hd:GovTalkMessage/hd:Body/fps:IRenvelope/fps:FullPaymentSubmission/fps:Employee/fps:Employment/fps:Payment/fps:Benefits/fps:Car/fps:FreeFuel/fps:Withdrawn" mode="M23" priority="4000">

		<!--ASSERT -->
<axsl:choose>
      <axsl:when test="(round(date:seconds(normalize-space(../fps:Provided)) div 86400) &lt;= round(date:seconds(normalize-space((.))) div 86400))"/>
      <axsl:otherwise>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="errorCode">7938</axsl:variable>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="defaultMessage">[FREEFUELWITHDRAWN] must not be before [FREEFUELPROVIDED]. Please check</axsl:variable>
        <err:Error xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" xmlns:dsl="http://decisionsoft.com/rim/errorExtension">
          <err:RaisedBy>ChRIS</err:RaisedBy>
          <err:Number>
            <axsl:value-of select="normalize-space($errorCode)"/>
          </err:Number>
          <err:Type>business</err:Type>
          <err:Text>
            <axsl:choose>
              <axsl:when test="normalize-space($defaultMessage)">
                <axsl:copy-of select="$defaultMessage"/>
              </axsl:when>
              <axsl:otherwise>[FREEFUELWITHDRAWN] must not be before [FREEFUELPROVIDED]</axsl:otherwise>
            </axsl:choose>
          </err:Text>
          <err:Location>
            <axsl:apply-templates mode="schematron-get-full-path" select="."/>
          </err:Location>
        </err:Error>
      </axsl:otherwise>
    </axsl:choose>
    <axsl:apply-templates mode="M23" select="@*|*|comment()|processing-instruction()"/>
  </axsl:template>
  <axsl:template match="text()" mode="M23" priority="-1"/>
  <axsl:template match="@*|node()" mode="M23" priority="-2">
    <axsl:apply-templates mode="M23" select="@*|node()"/>
  </axsl:template>

<!--PATTERN p24-->


	<!--RULE -->
<axsl:template match="/hd:GovTalkMessage/hd:Body/fps:IRenvelope/fps:FullPaymentSubmission/fps:Employee/fps:Employment/fps:Payment/fps:SPBPNIREYTD" mode="M24" priority="4000">

		<!--ASSERT -->
<axsl:choose>
      <axsl:when test="../fps:MiscarriageNIRE"/>
      <axsl:otherwise>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="errorCode">7956</axsl:variable>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="defaultMessage">If [STATUTORYPARENTALBEREAVEMENTPAYNIRE] is present, there must be an entry in [MISCARRIAGENIRE]. Please check.</axsl:variable>
        <err:Error xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" xmlns:dsl="http://decisionsoft.com/rim/errorExtension">
          <err:RaisedBy>ChRIS</err:RaisedBy>
          <err:Number>
            <axsl:value-of select="normalize-space($errorCode)"/>
          </err:Number>
          <err:Type>business</err:Type>
          <err:Text>
            <axsl:choose>
              <axsl:when test="normalize-space($defaultMessage)">
                <axsl:copy-of select="$defaultMessage"/>
              </axsl:when>
              <axsl:otherwise>If [STATUTORYPARENTALBEREAVEMENTPAYNIRE] is present the following should be true: [MISCARRIAGENIRE] is present</axsl:otherwise>
            </axsl:choose>
          </err:Text>
          <err:Location>
            <axsl:apply-templates mode="schematron-get-full-path" select="."/>
          </err:Location>
        </err:Error>
      </axsl:otherwise>
    </axsl:choose>

		<!--ASSERT -->
<axsl:choose>
      <axsl:when test="../fps:EmployeeWorkplacePostcodeNIRE"/>
      <axsl:otherwise>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="errorCode">7957</axsl:variable>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="defaultMessage">If [STATUTORYPARENTALBEREAVEMENTPAYNIRE] is present, there must be an entry in [EMPLOYEEWORKPLACEPOSTCODENIRE]. Please check.</axsl:variable>
        <err:Error xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" xmlns:dsl="http://decisionsoft.com/rim/errorExtension">
          <err:RaisedBy>ChRIS</err:RaisedBy>
          <err:Number>
            <axsl:value-of select="normalize-space($errorCode)"/>
          </err:Number>
          <err:Type>business</err:Type>
          <err:Text>
            <axsl:choose>
              <axsl:when test="normalize-space($defaultMessage)">
                <axsl:copy-of select="$defaultMessage"/>
              </axsl:when>
              <axsl:otherwise>If [STATUTORYPARENTALBEREAVEMENTPAYNIRE] is present the following should be true: [EMPLOYEEWORKPLACEPOSTCODENIRE] is present</axsl:otherwise>
            </axsl:choose>
          </err:Text>
          <err:Location>
            <axsl:apply-templates mode="schematron-get-full-path" select="."/>
          </err:Location>
        </err:Error>
      </axsl:otherwise>
    </axsl:choose>
    <axsl:apply-templates mode="M24" select="@*|*|comment()|processing-instruction()"/>
  </axsl:template>
  <axsl:template match="text()" mode="M24" priority="-1"/>
  <axsl:template match="@*|node()" mode="M24" priority="-2">
    <axsl:apply-templates mode="M24" select="@*|node()"/>
  </axsl:template>

<!--PATTERN p25-->


	<!--RULE -->
<axsl:template match="/hd:GovTalkMessage/hd:Body/fps:IRenvelope/fps:FullPaymentSubmission/fps:Employee/fps:Employment/fps:Payment/fps:TrivialCommutationPayment" mode="M25" priority="4000">

		<!--ASSERT -->
<axsl:choose>
      <axsl:when test="count(../fps:TrivialCommutationPayment/@type[. = current()/@type]) &lt;= 1"/>
      <axsl:otherwise>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="errorCode">7885</axsl:variable>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="defaultMessage">[TRIVIALCOMMUTATIONPAYMENTTYPE] should be unique. Please check</axsl:variable>
        <err:Error xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" xmlns:dsl="http://decisionsoft.com/rim/errorExtension">
          <err:RaisedBy>ChRIS</err:RaisedBy>
          <err:Number>
            <axsl:value-of select="normalize-space($errorCode)"/>
          </err:Number>
          <err:Type>business</err:Type>
          <err:Text>
            <axsl:choose>
              <axsl:when test="normalize-space($defaultMessage)">
                <axsl:copy-of select="$defaultMessage"/>
              </axsl:when>
              <axsl:otherwise>[TRIVIALCOMMUTATIONPAYMENTTYPE] should be unique within each [PAYMENT]</axsl:otherwise>
            </axsl:choose>
          </err:Text>
          <err:Location>
            <axsl:apply-templates mode="schematron-get-full-path" select="."/>
          </err:Location>
        </err:Error>
      </axsl:otherwise>
    </axsl:choose>
    <axsl:apply-templates mode="M25" select="@*|*|comment()|processing-instruction()"/>
  </axsl:template>
  <axsl:template match="text()" mode="M25" priority="-1"/>
  <axsl:template match="@*|node()" mode="M25" priority="-2">
    <axsl:apply-templates mode="M25" select="@*|node()"/>
  </axsl:template>

<!--PATTERN p26-->


	<!--RULE -->
<axsl:template match="/hd:GovTalkMessage/hd:Body/fps:IRenvelope/fps:FullPaymentSubmission/fps:Employee/fps:Employment/fps:Payment/fps:FlexibleDrawdown" mode="M26" priority="4000">

		<!--ASSERT -->
<axsl:choose>
      <axsl:when test="fps:TaxablePayment or fps:NontaxablePayment"/>
      <axsl:otherwise>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="errorCode">7936</axsl:variable>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="defaultMessage">If [FLEXIBLEDRAWDOWN] is present, there must be an entry in at least one of [TAXABLEPAYMENT] or [NONTAXABLEPAYMENT]. Please check.</axsl:variable>
        <err:Error xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" xmlns:dsl="http://decisionsoft.com/rim/errorExtension">
          <err:RaisedBy>ChRIS</err:RaisedBy>
          <err:Number>
            <axsl:value-of select="normalize-space($errorCode)"/>
          </err:Number>
          <err:Type>business</err:Type>
          <err:Text>
            <axsl:choose>
              <axsl:when test="normalize-space($defaultMessage)">
                <axsl:copy-of select="$defaultMessage"/>
              </axsl:when>
              <axsl:otherwise>If [FLEXIBLEDRAWDOWN] is present the following should be true: [TAXABLEPAYMENT] is present or [NONTAXABLEPAYMENT] is present</axsl:otherwise>
            </axsl:choose>
          </err:Text>
          <err:Location>
            <axsl:apply-templates mode="schematron-get-full-path" select="."/>
          </err:Location>
        </err:Error>
      </axsl:otherwise>
    </axsl:choose>
    <axsl:apply-templates mode="M26" select="@*|*|comment()|processing-instruction()"/>
  </axsl:template>
  <axsl:template match="text()" mode="M26" priority="-1"/>
  <axsl:template match="@*|node()" mode="M26" priority="-2">
    <axsl:apply-templates mode="M26" select="@*|node()"/>
  </axsl:template>

<!--PATTERN p27-->


	<!--RULE -->
<axsl:template match="/hd:GovTalkMessage/hd:Body/fps:IRenvelope/fps:FullPaymentSubmission/fps:Employee/fps:Employment/fps:NIlettersAndValues/fps:NIletter" mode="M27" priority="4000">

		<!--ASSERT -->
<axsl:choose>
      <axsl:when test="not (../../../fps:EmployeeDetails/fps:Gender = 'M')               or               not ( (. = 'B') or (. = 'E') or (. = 'T') or (. = 'I'))"/>
      <axsl:otherwise>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="errorCode">7849</axsl:variable>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="defaultMessage">The NI Letter cannot be B or E or I or T if [GENDER] is shown as male. Please check</axsl:variable>
        <err:Error xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" xmlns:dsl="http://decisionsoft.com/rim/errorExtension">
          <err:RaisedBy>ChRIS</err:RaisedBy>
          <err:Number>
            <axsl:value-of select="normalize-space($errorCode)"/>
          </err:Number>
          <err:Type>business</err:Type>
          <err:Text>
            <axsl:choose>
              <axsl:when test="normalize-space($defaultMessage)">
                <axsl:copy-of select="$defaultMessage"/>
              </axsl:when>
              <axsl:otherwise>If [GENDER] is 'M', [NILETTER] cannot equal 'B' or 'E' or 'I' or 'T'</axsl:otherwise>
            </axsl:choose>
          </err:Text>
          <err:Location>
            <axsl:apply-templates mode="schematron-get-full-path" select="."/>
          </err:Location>
        </err:Error>
      </axsl:otherwise>
    </axsl:choose>

		<!--ASSERT -->
<axsl:choose>
      <axsl:when test="count(../../fps:NIlettersAndValues/fps:NIletter[. = current()]) = 1"/>
      <axsl:otherwise>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="errorCode">7850</axsl:variable>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="defaultMessage">The [NILETTER] must be unique within each occurrence of the [EMPLOYMENT] group. Please check</axsl:variable>
        <err:Error xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" xmlns:dsl="http://decisionsoft.com/rim/errorExtension">
          <err:RaisedBy>ChRIS</err:RaisedBy>
          <err:Number>
            <axsl:value-of select="normalize-space($errorCode)"/>
          </err:Number>
          <err:Type>business</err:Type>
          <err:Text>
            <axsl:choose>
              <axsl:when test="normalize-space($defaultMessage)">
                <axsl:copy-of select="$defaultMessage"/>
              </axsl:when>
              <axsl:otherwise>[NILETTER] must be unique within each occurrence of the [EMPLOYMENT] group</axsl:otherwise>
            </axsl:choose>
          </err:Text>
          <err:Location>
            <axsl:apply-templates mode="schematron-get-full-path" select="."/>
          </err:Location>
        </err:Error>
      </axsl:otherwise>
    </axsl:choose>

		<!--ASSERT -->
<axsl:choose>
      <axsl:when test="not((. = 'F') or                (. = 'I') or                (. = 'L') or                (. = 'S') or               (. = 'N') or                (. = 'E') or                (. = 'D') or                (. = 'K'))               or ../../fps:EmployeeWorkplacePostcode"/>
      <axsl:otherwise>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="errorCode">7954</axsl:variable>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="defaultMessage">If the [NILETTER] is 'F', 'I', 'L', 'S', 'N', 'E', 'D' or K', then [EMPLOYEEWORKPLACEPOSTCODE] must be present. Please check</axsl:variable>
        <err:Error xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" xmlns:dsl="http://decisionsoft.com/rim/errorExtension">
          <err:RaisedBy>ChRIS</err:RaisedBy>
          <err:Number>
            <axsl:value-of select="normalize-space($errorCode)"/>
          </err:Number>
          <err:Type>business</err:Type>
          <err:Text>
            <axsl:choose>
              <axsl:when test="normalize-space($defaultMessage)">
                <axsl:copy-of select="$defaultMessage"/>
              </axsl:when>
              <axsl:otherwise>[EMPLOYEEWORKPLACEPOSTCODE] should be present if [NILETTER] eq 'F' or [NILETTER] eq 'I' or [NILETTER] eq 'L' or [NILETTER] eq 'S' or [NILETTER] eq 'N' or [NILETTER] eq 'E' or [NILETTER] eq 'D' or [NILETTER] eq 'K'</axsl:otherwise>
            </axsl:choose>
          </err:Text>
          <err:Location>
            <axsl:apply-templates mode="schematron-get-full-path" select="."/>
          </err:Location>
        </err:Error>
      </axsl:otherwise>
    </axsl:choose>

		<!--ASSERT -->
<axsl:choose>
      <axsl:when test="(round(date:seconds(normalize-space(../../../fps:EmployeeDetails/fps:BirthDate)) div 86400) &lt;= round(date:seconds(normalize-space('1961-04-05')) div 86400))               or               not((. = 'B') or (. = 'E') or (. = 'T') or (. = 'I'))"/>
      <axsl:otherwise>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="errorCode">7955</axsl:variable>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="defaultMessage">The NI Letter cannot be B or E or I or T if [DATEOFBIRTH] is after 5 April 1961. Please check</axsl:variable>
        <err:Error xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" xmlns:dsl="http://decisionsoft.com/rim/errorExtension">
          <err:RaisedBy>ChRIS</err:RaisedBy>
          <err:Number>
            <axsl:value-of select="normalize-space($errorCode)"/>
          </err:Number>
          <err:Type>business</err:Type>
          <err:Text>
            <axsl:choose>
              <axsl:when test="normalize-space($defaultMessage)">
                <axsl:copy-of select="$defaultMessage"/>
              </axsl:when>
              <axsl:otherwise>If [DATEOFBIRTH] is after '1961-04-05', [NILETTER] cannot equal 'B' or 'E' or 'I' or 'T'</axsl:otherwise>
            </axsl:choose>
          </err:Text>
          <err:Location>
            <axsl:apply-templates mode="schematron-get-full-path" select="."/>
          </err:Location>
        </err:Error>
      </axsl:otherwise>
    </axsl:choose>
    <axsl:apply-templates mode="M27" select="@*|*|comment()|processing-instruction()"/>
  </axsl:template>
  <axsl:template match="text()" mode="M27" priority="-1"/>
  <axsl:template match="@*|node()" mode="M27" priority="-2">
    <axsl:apply-templates mode="M27" select="@*|node()"/>
  </axsl:template>

<!--PATTERN p28-->


	<!--RULE -->
<axsl:template match="/hd:GovTalkMessage/hd:Body/fps:IRenvelope/fps:FullPaymentSubmission/fps:Employee/fps:Employment/fps:NIlettersAndValues/fps:AtLELYTD" mode="M28" priority="4000">

		<!--ASSERT -->
<axsl:choose>
      <axsl:when test="not (../fps:NIletter = 'X')               or             . = 0"/>
      <axsl:otherwise>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="errorCode">7852</axsl:variable>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="defaultMessage">The amount in [Earnings at LEL] must be 0.00 if the [NILETTER] is 'X'. Please check</axsl:variable>
        <err:Error xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" xmlns:dsl="http://decisionsoft.com/rim/errorExtension">
          <err:RaisedBy>ChRIS</err:RaisedBy>
          <err:Number>
            <axsl:value-of select="normalize-space($errorCode)"/>
          </err:Number>
          <err:Type>business</err:Type>
          <err:Text>
            <axsl:choose>
              <axsl:when test="normalize-space($defaultMessage)">
                <axsl:copy-of select="$defaultMessage"/>
              </axsl:when>
              <axsl:otherwise>[Earnings at LEL] must be zero if [NILETTER] is 'X'</axsl:otherwise>
            </axsl:choose>
          </err:Text>
          <err:Location>
            <axsl:apply-templates mode="schematron-get-full-path" select="."/>
          </err:Location>
        </err:Error>
      </axsl:otherwise>
    </axsl:choose>
    <axsl:apply-templates mode="M28" select="@*|*|comment()|processing-instruction()"/>
  </axsl:template>
  <axsl:template match="text()" mode="M28" priority="-1"/>
  <axsl:template match="@*|node()" mode="M28" priority="-2">
    <axsl:apply-templates mode="M28" select="@*|node()"/>
  </axsl:template>

<!--PATTERN p29-->


	<!--RULE -->
<axsl:template match="/hd:GovTalkMessage/hd:Body/fps:IRenvelope/fps:FullPaymentSubmission/fps:Employee/fps:Employment/fps:NIlettersAndValues/fps:LELtoPTYTD" mode="M29" priority="4000">

		<!--ASSERT -->
<axsl:choose>
      <axsl:when test="not (../fps:NIletter = 'X')               or             . = 0"/>
      <axsl:otherwise>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="errorCode">7853</axsl:variable>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="defaultMessage">The amount in [Earnings above LEL to PT] must be 0.00 if the [NILETTER] is 'X'. Please check</axsl:variable>
        <err:Error xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" xmlns:dsl="http://decisionsoft.com/rim/errorExtension">
          <err:RaisedBy>ChRIS</err:RaisedBy>
          <err:Number>
            <axsl:value-of select="normalize-space($errorCode)"/>
          </err:Number>
          <err:Type>business</err:Type>
          <err:Text>
            <axsl:choose>
              <axsl:when test="normalize-space($defaultMessage)">
                <axsl:copy-of select="$defaultMessage"/>
              </axsl:when>
              <axsl:otherwise>[Earnings above LEL to PT] must be zero if [NILETTER] is 'X'</axsl:otherwise>
            </axsl:choose>
          </err:Text>
          <err:Location>
            <axsl:apply-templates mode="schematron-get-full-path" select="."/>
          </err:Location>
        </err:Error>
      </axsl:otherwise>
    </axsl:choose>
    <axsl:apply-templates mode="M29" select="@*|*|comment()|processing-instruction()"/>
  </axsl:template>
  <axsl:template match="text()" mode="M29" priority="-1"/>
  <axsl:template match="@*|node()" mode="M29" priority="-2">
    <axsl:apply-templates mode="M29" select="@*|node()"/>
  </axsl:template>

<!--PATTERN p30-->


	<!--RULE -->
<axsl:template match="/hd:GovTalkMessage/hd:Body/fps:IRenvelope/fps:FullPaymentSubmission/fps:Employee/fps:Employment/fps:NIlettersAndValues/fps:PTtoUELYTD" mode="M30" priority="4000">

		<!--ASSERT -->
<axsl:choose>
      <axsl:when test="not (../fps:NIletter = 'X')             or               . = 0"/>
      <axsl:otherwise>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="errorCode">7854</axsl:variable>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="defaultMessage">The amount in [Earnings above PT up to UEL] must be 0.00 if the [NILETTER] is 'X'. Please check</axsl:variable>
        <err:Error xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" xmlns:dsl="http://decisionsoft.com/rim/errorExtension">
          <err:RaisedBy>ChRIS</err:RaisedBy>
          <err:Number>
            <axsl:value-of select="normalize-space($errorCode)"/>
          </err:Number>
          <err:Type>business</err:Type>
          <err:Text>
            <axsl:choose>
              <axsl:when test="normalize-space($defaultMessage)">
                <axsl:copy-of select="$defaultMessage"/>
              </axsl:when>
              <axsl:otherwise>[Earnings above PT up to UEL] must be zero if [NILETTER] is 'X'</axsl:otherwise>
            </axsl:choose>
          </err:Text>
          <err:Location>
            <axsl:apply-templates mode="schematron-get-full-path" select="."/>
          </err:Location>
        </err:Error>
      </axsl:otherwise>
    </axsl:choose>
    <axsl:apply-templates mode="M30" select="@*|*|comment()|processing-instruction()"/>
  </axsl:template>
  <axsl:template match="text()" mode="M30" priority="-1"/>
  <axsl:template match="@*|node()" mode="M30" priority="-2">
    <axsl:apply-templates mode="M30" select="@*|node()"/>
  </axsl:template>

<!--PATTERN p31-->


	<!--RULE -->
<axsl:template match="/hd:GovTalkMessage/hd:Body/fps:IRenvelope/fps:FullPaymentSubmission/fps:Employee/fps:Employment/fps:NIlettersAndValues/fps:TotalEmpNICInPd" mode="M31" priority="4000">

		<!--ASSERT -->
<axsl:choose>
      <axsl:when test="not(../fps:NIletter = 'X') or . = 0"/>
      <axsl:otherwise>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="errorCode">7863</axsl:variable>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="defaultMessage">The amount in [TOTALEMPLOYERNICONTRIBUTIONS] must be 0.00 if the [NILETTER] is 'X'. Please check</axsl:variable>
        <err:Error xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" xmlns:dsl="http://decisionsoft.com/rim/errorExtension">
          <err:RaisedBy>ChRIS</err:RaisedBy>
          <err:Number>
            <axsl:value-of select="normalize-space($errorCode)"/>
          </err:Number>
          <err:Type>business</err:Type>
          <err:Text>
            <axsl:choose>
              <axsl:when test="normalize-space($defaultMessage)">
                <axsl:copy-of select="$defaultMessage"/>
              </axsl:when>
              <axsl:otherwise>This must be 0.00 if [NILETTER] is 'X'.</axsl:otherwise>
            </axsl:choose>
          </err:Text>
          <err:Location>
            <axsl:apply-templates mode="schematron-get-full-path" select="."/>
          </err:Location>
        </err:Error>
      </axsl:otherwise>
    </axsl:choose>
    <axsl:apply-templates mode="M31" select="@*|*|comment()|processing-instruction()"/>
  </axsl:template>
  <axsl:template match="text()" mode="M31" priority="-1"/>
  <axsl:template match="@*|node()" mode="M31" priority="-2">
    <axsl:apply-templates mode="M31" select="@*|node()"/>
  </axsl:template>

<!--PATTERN p32-->


	<!--RULE -->
<axsl:template match="/hd:GovTalkMessage/hd:Body/fps:IRenvelope/fps:FullPaymentSubmission/fps:Employee/fps:Employment/fps:NIlettersAndValues/fps:TotalEmpNICYTD" mode="M32" priority="4000">

		<!--ASSERT -->
<axsl:choose>
      <axsl:when test="not(../fps:NIletter = 'X') or . = 0"/>
      <axsl:otherwise>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="errorCode">7864</axsl:variable>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="defaultMessage">The amount in [TOTALEMPLOYERNICONTRIBUTIONSYEARTODATE] must be 0.00 if the [NILETTER] is 'X'. Please check</axsl:variable>
        <err:Error xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" xmlns:dsl="http://decisionsoft.com/rim/errorExtension">
          <err:RaisedBy>ChRIS</err:RaisedBy>
          <err:Number>
            <axsl:value-of select="normalize-space($errorCode)"/>
          </err:Number>
          <err:Type>business</err:Type>
          <err:Text>
            <axsl:choose>
              <axsl:when test="normalize-space($defaultMessage)">
                <axsl:copy-of select="$defaultMessage"/>
              </axsl:when>
              <axsl:otherwise>This must be 0.00 if [NILETTER] is 'X'.</axsl:otherwise>
            </axsl:choose>
          </err:Text>
          <err:Location>
            <axsl:apply-templates mode="schematron-get-full-path" select="."/>
          </err:Location>
        </err:Error>
      </axsl:otherwise>
    </axsl:choose>
    <axsl:apply-templates mode="M32" select="@*|*|comment()|processing-instruction()"/>
  </axsl:template>
  <axsl:template match="text()" mode="M32" priority="-1"/>
  <axsl:template match="@*|node()" mode="M32" priority="-2">
    <axsl:apply-templates mode="M32" select="@*|node()"/>
  </axsl:template>

<!--PATTERN p33-->


	<!--RULE -->
<axsl:template match="/hd:GovTalkMessage/hd:Body/fps:IRenvelope/fps:FullPaymentSubmission/fps:Employee/fps:Employment/fps:NIlettersAndValues/fps:EmpeeContribnsInPd" mode="M33" priority="4000">

		<!--ASSERT -->
<axsl:choose>
      <axsl:when test="not(../fps:NIletter = 'X' or ../fps:NIletter = 'C' or ../fps:NIletter = 'K' or ../fps:NIletter = 'S' or ../fps:NIletter = 'W') or . = 0"/>
      <axsl:otherwise>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="errorCode">7865</axsl:variable>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="defaultMessage">The amount in [EMPLOYEESCONTRIBUTIONSONALLEARNINGS] must be 0.00 if the [NILETTER] is 'X', 'C', 'K', 'S' or 'W'. Please check</axsl:variable>
        <err:Error xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" xmlns:dsl="http://decisionsoft.com/rim/errorExtension">
          <err:RaisedBy>ChRIS</err:RaisedBy>
          <err:Number>
            <axsl:value-of select="normalize-space($errorCode)"/>
          </err:Number>
          <err:Type>business</err:Type>
          <err:Text>
            <axsl:choose>
              <axsl:when test="normalize-space($defaultMessage)">
                <axsl:copy-of select="$defaultMessage"/>
              </axsl:when>
              <axsl:otherwise>This must be 0.00 if [NILETTER] is 'X', 'C', 'K', 'S' or 'W'.</axsl:otherwise>
            </axsl:choose>
          </err:Text>
          <err:Location>
            <axsl:apply-templates mode="schematron-get-full-path" select="."/>
          </err:Location>
        </err:Error>
      </axsl:otherwise>
    </axsl:choose>
    <axsl:apply-templates mode="M33" select="@*|*|comment()|processing-instruction()"/>
  </axsl:template>
  <axsl:template match="text()" mode="M33" priority="-1"/>
  <axsl:template match="@*|node()" mode="M33" priority="-2">
    <axsl:apply-templates mode="M33" select="@*|node()"/>
  </axsl:template>

<!--PATTERN p34-->


	<!--RULE -->
<axsl:template match="/hd:GovTalkMessage/hd:Body/fps:IRenvelope/fps:FullPaymentSubmission/fps:Employee/fps:Employment/fps:NIlettersAndValues/fps:EmpeeContribnsYTD" mode="M34" priority="4000">

		<!--ASSERT -->
<axsl:choose>
      <axsl:when test="not(../fps:NIletter = 'X' or ../fps:NIletter = 'C' or ../fps:NIletter = 'K' or ../fps:NIletter = 'S' or ../fps:NIletter = 'W') or . = 0"/>
      <axsl:otherwise>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="errorCode">7866</axsl:variable>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="defaultMessage">The amount in [EMPLOYEESCONTRIBUTIONSONALLEARNINGSYEARTODATE] must be 0.00 if the [NILETTER] is 'X', 'C', 'K', 'S' or 'W'. Please check</axsl:variable>
        <err:Error xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" xmlns:dsl="http://decisionsoft.com/rim/errorExtension">
          <err:RaisedBy>ChRIS</err:RaisedBy>
          <err:Number>
            <axsl:value-of select="normalize-space($errorCode)"/>
          </err:Number>
          <err:Type>business</err:Type>
          <err:Text>
            <axsl:choose>
              <axsl:when test="normalize-space($defaultMessage)">
                <axsl:copy-of select="$defaultMessage"/>
              </axsl:when>
              <axsl:otherwise>This must be 0.00 if [NILETTER] is 'X', 'C', 'K', 'S' or 'W'.</axsl:otherwise>
            </axsl:choose>
          </err:Text>
          <err:Location>
            <axsl:apply-templates mode="schematron-get-full-path" select="."/>
          </err:Location>
        </err:Error>
      </axsl:otherwise>
    </axsl:choose>
    <axsl:apply-templates mode="M34" select="@*|*|comment()|processing-instruction()"/>
  </axsl:template>
  <axsl:template match="text()" mode="M34" priority="-1"/>
  <axsl:template match="@*|node()" mode="M34" priority="-2">
    <axsl:apply-templates mode="M34" select="@*|node()"/>
  </axsl:template>

<!--PATTERN p14-->


	<!--RULE -->
<axsl:template match="/hd:GovTalkMessage/hd:Body/fps:IRenvelope/fps:FullPaymentSubmission/fps:Employee/fps:Employment" mode="M35" priority="4000">

		<!--ASSERT -->
<axsl:choose>
      <axsl:when test="not (fps:Starter/fps:StartDate)                 or                   fps:Starter/fps:StartDec                 or                   fps:Starter/fps:Seconded/fps:Stay183DaysOrMore                 or                   fps:Starter/fps:Seconded/fps:StayLessThan183Days                 or                   fps:Starter/fps:Seconded/fps:InOutUK                 or                   fps:Starter/fps:OccPension/fps:Amount &gt; 0"/>
      <axsl:otherwise>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="errorCode">7878</axsl:variable>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="defaultMessage">If [STARTDATE] is completed, at least one of [STARTINGDECLARATION], [INTENDTOSTAYOVER183DAYS], [INTENDTOSTAYLESSTHAN183DAYS], [INTENDTOWORKBOTHINANDOUTOFUK] must be present or [ANNUALAMOUNTOFPENSION] must be greater than zero. Please check</axsl:variable>
        <err:Error xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" xmlns:dsl="http://decisionsoft.com/rim/errorExtension">
          <err:RaisedBy>ChRIS</err:RaisedBy>
          <err:Number>
            <axsl:value-of select="normalize-space($errorCode)"/>
          </err:Number>
          <err:Type>business</err:Type>
          <err:Text>
            <axsl:choose>
              <axsl:when test="normalize-space($defaultMessage)">
                <axsl:copy-of select="$defaultMessage"/>
              </axsl:when>
              <axsl:otherwise>If [STARTDATE] is present, at least one of [STARTINGDECLARATION], [INTENDTOSTAYOVER183DAYS], [INTENDTOSTAYLESSTHAN183DAYS], [INTENDTOWORKBOTHINANDOUTOFUK] must be present or [ANNUALAMOUNTOFPENSION] must be greater than zero</axsl:otherwise>
            </axsl:choose>
          </err:Text>
          <err:Location>
            <axsl:apply-templates mode="schematron-get-full-path" select="."/>
          </err:Location>
        </err:Error>
      </axsl:otherwise>
    </axsl:choose>

		<!--ASSERT -->
<axsl:choose>
      <axsl:when test="not (                     fps:OccPenInd                   and                     fps:Starter/fps:OccPension/fps:Amount                   and                     fps:Starter/fps:StartDec                 )"/>
      <axsl:otherwise>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="errorCode">7879</axsl:variable>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="defaultMessage">You cannot complete [STARTINGDECLARATION] if both of [OCCPENIND] and [ANNUALAMOUNTOFPENSION] are present</axsl:variable>
        <err:Error xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" xmlns:dsl="http://decisionsoft.com/rim/errorExtension">
          <err:RaisedBy>ChRIS</err:RaisedBy>
          <err:Number>
            <axsl:value-of select="normalize-space($errorCode)"/>
          </err:Number>
          <err:Type>business</err:Type>
          <err:Text>
            <axsl:choose>
              <axsl:when test="normalize-space($defaultMessage)">
                <axsl:copy-of select="$defaultMessage"/>
              </axsl:when>
              <axsl:otherwise>[STARTINGDECLARATION] is prohibited if both of [OCCPENIND] and [ANNUALAMOUNTOFPENSION] are present</axsl:otherwise>
            </axsl:choose>
          </err:Text>
          <err:Location>
            <axsl:apply-templates mode="schematron-get-full-path" select="."/>
          </err:Location>
        </err:Error>
      </axsl:otherwise>
    </axsl:choose>

		<!--ASSERT -->
<axsl:choose>
      <axsl:when test="not (                     fps:Starter/fps:Seconded/fps:Stay183DaysOrMore                   or                     fps:Starter/fps:Seconded/fps:StayLessThan183Days                   or                     fps:Starter/fps:Seconded/fps:InOutUK                 )                 or                 not (                   fps:Starter/fps:StartDec                 )"/>
      <axsl:otherwise>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="errorCode">7880</axsl:variable>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="defaultMessage">You cannot complete [STARTINGDECLARATION] if any of [INTENDTOSTAYOVER183DAYS], [INTENDTOSTAYLESSTHAN183DAYS], [INTENDTOWORKBOTHINANDOUTOFUK] are present.</axsl:variable>
        <err:Error xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" xmlns:dsl="http://decisionsoft.com/rim/errorExtension">
          <err:RaisedBy>ChRIS</err:RaisedBy>
          <err:Number>
            <axsl:value-of select="normalize-space($errorCode)"/>
          </err:Number>
          <err:Type>business</err:Type>
          <err:Text>
            <axsl:choose>
              <axsl:when test="normalize-space($defaultMessage)">
                <axsl:copy-of select="$defaultMessage"/>
              </axsl:when>
              <axsl:otherwise>[STARTINGDECLARATION] is prohibited if any of [INTENDTOSTAYOVER183DAYS], [INTENDTOSTAYLESSTHAN183DAYS], [INTENDTOWORKBOTHINANDOUTOFUK] are present.</axsl:otherwise>
            </axsl:choose>
          </err:Text>
          <err:Location>
            <axsl:apply-templates mode="schematron-get-full-path" select="."/>
          </err:Location>
        </err:Error>
      </axsl:otherwise>
    </axsl:choose>

		<!--ASSERT -->
<axsl:choose>
      <axsl:when test="(                     fps:OccPenInd                   and                     fps:Starter/fps:OccPension/fps:Amount                 )                   or                 (                     fps:Starter/fps:Seconded/fps:Stay183DaysOrMore                   or                     fps:Starter/fps:Seconded/fps:StayLessThan183Days                   or                     fps:Starter/fps:Seconded/fps:InOutUK                 )                 or not (                     fps:Starter/fps:StartDate                 )                 or                     fps:Starter/fps:StartDec"/>
      <axsl:otherwise>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="errorCode">7881</axsl:variable>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="defaultMessage">You must complete [STARTINGDECLARATION] if [STARTDATE] is present, unless there is an entry in any of [INTENDTOSTAYOVER183DAYS], [INTENDTOSTAYLESSTHAN183DAYS], [INTENDTOWORKBOTHINANDOUTOFUK], or both [OCCPENIND] and [ANNUALAMOUNTOFPENSION]. Please check.</axsl:variable>
        <err:Error xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" xmlns:dsl="http://decisionsoft.com/rim/errorExtension">
          <err:RaisedBy>ChRIS</err:RaisedBy>
          <err:Number>
            <axsl:value-of select="normalize-space($errorCode)"/>
          </err:Number>
          <err:Type>business</err:Type>
          <err:Text>
            <axsl:choose>
              <axsl:when test="normalize-space($defaultMessage)">
                <axsl:copy-of select="$defaultMessage"/>
              </axsl:when>
              <axsl:otherwise>[STARTINGDECLARATION] is mandatory if [STARTDATE] is present, unless any of [INTENDTOSTAYOVER183DAYS], [INTENDTOSTAYLESSTHAN183DAYS], [INTENDTOWORKBOTHINANDOUTOFUK] are present, or both [OCCPENIND] and [ANNUALAMOUNTOFPENSION] are present.</axsl:otherwise>
            </axsl:choose>
          </err:Text>
          <err:Location>
            <axsl:apply-templates mode="schematron-get-full-path" select="."/>
          </err:Location>
        </err:Error>
      </axsl:otherwise>
    </axsl:choose>

		<!--ASSERT -->
<axsl:choose>
      <axsl:when test="not ( fps:Starter/fps:OccPension/fps:Amount )                 or                   fps:OccPenInd"/>
      <axsl:otherwise>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="errorCode">7916</axsl:variable>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="defaultMessage">If there is an entry in [ANNUALAMOUNTOFPENSION], then [OCCPENIND] must be completed. Please check.</axsl:variable>
        <err:Error xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" xmlns:dsl="http://decisionsoft.com/rim/errorExtension">
          <err:RaisedBy>ChRIS</err:RaisedBy>
          <err:Number>
            <axsl:value-of select="normalize-space($errorCode)"/>
          </err:Number>
          <err:Type>business</err:Type>
          <err:Text>
            <axsl:choose>
              <axsl:when test="normalize-space($defaultMessage)">
                <axsl:copy-of select="$defaultMessage"/>
              </axsl:when>
              <axsl:otherwise>If [ANNUALAMOUNTOFPENSION] is present then [OCCPENIND] should be present.</axsl:otherwise>
            </axsl:choose>
          </err:Text>
          <err:Location>
            <axsl:apply-templates mode="schematron-get-full-path" select="."/>
          </err:Location>
        </err:Error>
      </axsl:otherwise>
    </axsl:choose>

		<!--ASSERT -->
<axsl:choose>
      <axsl:when test="not ( fps:Starter )               or                 fps:Starter/fps:StartDate               or                 fps:Starter/fps:StartDec               or                 fps:Starter/fps:StudentLoan               or                 fps:Starter/fps:PostgradLoan               or                 fps:Starter/fps:Seconded               or                 fps:Starter/fps:OccPension               or                 fps:Starter/fps:StatePension"/>
      <axsl:otherwise>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="errorCode">7934</axsl:variable>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="defaultMessage">If [STARTERINFORMATION] is present then an entry in [STARTDATE], [STARTINGDECLARATION], [HASSTUDENTLOAN], [HASPOSTGRADUATELOAN], [INDIVIDUALSECONDEDTOWORKINUK], [PENSIONSTART] or [PENSIONSTART] should be present. Please check.</axsl:variable>
        <err:Error xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" xmlns:dsl="http://decisionsoft.com/rim/errorExtension">
          <err:RaisedBy>ChRIS</err:RaisedBy>
          <err:Number>
            <axsl:value-of select="normalize-space($errorCode)"/>
          </err:Number>
          <err:Type>business</err:Type>
          <err:Text>
            <axsl:choose>
              <axsl:when test="normalize-space($defaultMessage)">
                <axsl:copy-of select="$defaultMessage"/>
              </axsl:when>
              <axsl:otherwise>If [STARTERINFORMATION] is present then [STARTDATE], [STARTINGDECLARATION], [HASSTUDENTLOAN], [HASPOSTGRADUATELOAN], [INDIVIDUALSECONDEDTOWORKINUK], [PENSIONSTART] or [PENSIONSTART] should be present</axsl:otherwise>
            </axsl:choose>
          </err:Text>
          <err:Location>
            <axsl:apply-templates mode="schematron-get-full-path" select="."/>
          </err:Location>
        </err:Error>
      </axsl:otherwise>
    </axsl:choose>
    <axsl:apply-templates mode="M35" select="@*|*|comment()|processing-instruction()"/>
  </axsl:template>
  <axsl:template match="text()" mode="M35" priority="-1"/>
  <axsl:template match="@*|node()" mode="M35" priority="-2">
    <axsl:apply-templates mode="M35" select="@*|node()"/>
  </axsl:template>

<!--PATTERN p9-->


	<!--RULE -->
<axsl:template match="/hd:GovTalkMessage/hd:Body/fps:IRenvelope/fps:FullPaymentSubmission/fps:Employee" mode="M36" priority="4000">

		<!--ASSERT -->
<axsl:choose>
      <axsl:when test="not ( fps:EmployeeDetails/fps:PartnerDetails )               or                 fps:Employment/fps:Payment/fps:ShPPYTD"/>
      <axsl:otherwise>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="errorCode">7845</axsl:variable>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="defaultMessage">There is an entry in [PARTNERDETAILS]. This is only relevant if [SHAREDPARENTALPAY] is included in the submission. Please check</axsl:variable>
        <err:Error xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" xmlns:dsl="http://decisionsoft.com/rim/errorExtension">
          <err:RaisedBy>ChRIS</err:RaisedBy>
          <err:Number>
            <axsl:value-of select="normalize-space($errorCode)"/>
          </err:Number>
          <err:Type>business</err:Type>
          <err:Text>
            <axsl:choose>
              <axsl:when test="normalize-space($defaultMessage)">
                <axsl:copy-of select="$defaultMessage"/>
              </axsl:when>
              <axsl:otherwise>If [PARTNERDETAILS] is present then [SHAREDPARENTALPAY] must be present</axsl:otherwise>
            </axsl:choose>
          </err:Text>
          <err:Location>
            <axsl:apply-templates mode="schematron-get-full-path" select="."/>
          </err:Location>
        </err:Error>
      </axsl:otherwise>
    </axsl:choose>

		<!--ASSERT -->
<axsl:choose>
      <axsl:when test="fps:Employment/fps:PaymentToANonIndividual                 or               fps:EmployeeDetails/fps:BirthDate"/>
      <axsl:otherwise>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="errorCode">7907</axsl:variable>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="defaultMessage">There must be an entry in [DATEOFBIRTH] if there is no entry in [PAYMENTTOANONINDIVIDUAL]. Please check.</axsl:variable>
        <err:Error xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" xmlns:dsl="http://decisionsoft.com/rim/errorExtension">
          <err:RaisedBy>ChRIS</err:RaisedBy>
          <err:Number>
            <axsl:value-of select="normalize-space($errorCode)"/>
          </err:Number>
          <err:Type>business</err:Type>
          <err:Text>
            <axsl:choose>
              <axsl:when test="normalize-space($defaultMessage)">
                <axsl:copy-of select="$defaultMessage"/>
              </axsl:when>
              <axsl:otherwise>[DATEOFBIRTH] is mandatory if [PAYMENTTOANONINDIVIDUAL] is absent.</axsl:otherwise>
            </axsl:choose>
          </err:Text>
          <err:Location>
            <axsl:apply-templates mode="schematron-get-full-path" select="."/>
          </err:Location>
        </err:Error>
      </axsl:otherwise>
    </axsl:choose>

		<!--ASSERT -->
<axsl:choose>
      <axsl:when test="not ( fps:EmployeeDetails/fps:Address )               or                 fps:EmployeeDetails/fps:Address/fps:Line               or                 fps:EmployeeDetails/fps:Address/fps:UKPostcode"/>
      <axsl:otherwise>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="errorCode">7932</axsl:variable>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="defaultMessage">If [ADDRESS] is present then an entry in [ADDRESSLINE] or [POSTCODE] must be present. Please check.</axsl:variable>
        <err:Error xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" xmlns:dsl="http://decisionsoft.com/rim/errorExtension">
          <err:RaisedBy>ChRIS</err:RaisedBy>
          <err:Number>
            <axsl:value-of select="normalize-space($errorCode)"/>
          </err:Number>
          <err:Type>business</err:Type>
          <err:Text>
            <axsl:choose>
              <axsl:when test="normalize-space($defaultMessage)">
                <axsl:copy-of select="$defaultMessage"/>
              </axsl:when>
              <axsl:otherwise>If [ADDRESS] is present then [ADDRESSLINE] or [POSTCODE] should be present</axsl:otherwise>
            </axsl:choose>
          </err:Text>
          <err:Location>
            <axsl:apply-templates mode="schematron-get-full-path" select="."/>
          </err:Location>
        </err:Error>
      </axsl:otherwise>
    </axsl:choose>
    <axsl:apply-templates mode="M36" select="@*|*|comment()|processing-instruction()"/>
  </axsl:template>
  <axsl:template match="text()" mode="M36" priority="-1"/>
  <axsl:template match="@*|node()" mode="M36" priority="-2">
    <axsl:apply-templates mode="M36" select="@*|node()"/>
  </axsl:template>

<!--PATTERN p36-->


	<!--RULE -->
<axsl:template match="/hd:GovTalkMessage/hd:Body/fps:IRenvelope/fps:FullPaymentSubmission/fps:FinalSubmission/fps:BecauseSchemeCeased" mode="M37" priority="4000">

		<!--ASSERT -->
<axsl:choose>
      <axsl:when test="../fps:DateSchemeCeased"/>
      <axsl:otherwise>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="errorCode">7875</axsl:variable>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="defaultMessage">[DATESCHEMECEASED] must be completed if [FINALSUBMISSIONCEASEDINDICATOR] is present</axsl:variable>
        <err:Error xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" xmlns:dsl="http://decisionsoft.com/rim/errorExtension">
          <err:RaisedBy>ChRIS</err:RaisedBy>
          <err:Number>
            <axsl:value-of select="normalize-space($errorCode)"/>
          </err:Number>
          <err:Type>business</err:Type>
          <err:Text>
            <axsl:choose>
              <axsl:when test="normalize-space($defaultMessage)">
                <axsl:copy-of select="$defaultMessage"/>
              </axsl:when>
              <axsl:otherwise>[DATESCHEMECEASED] should be present if [FINALSUBMISSIONCEASEDINDICATOR] is present</axsl:otherwise>
            </axsl:choose>
          </err:Text>
          <err:Location>
            <axsl:apply-templates mode="schematron-get-full-path" select="."/>
          </err:Location>
        </err:Error>
      </axsl:otherwise>
    </axsl:choose>
    <axsl:apply-templates mode="M37" select="@*|*|comment()|processing-instruction()"/>
  </axsl:template>
  <axsl:template match="text()" mode="M37" priority="-1"/>
  <axsl:template match="@*|node()" mode="M37" priority="-2">
    <axsl:apply-templates mode="M37" select="@*|node()"/>
  </axsl:template>

<!--PATTERN p37-->


	<!--RULE -->
<axsl:template match="/hd:GovTalkMessage/hd:Body/fps:IRenvelope/fps:FullPaymentSubmission/fps:FinalSubmission/fps:DateSchemeCeased" mode="M38" priority="4000">

		<!--ASSERT -->
<axsl:choose>
      <axsl:when test="(round(date:seconds(normalize-space(.)) div 86400) &lt;= round(date:seconds(normalize-space(date:date())) div 86400))"/>
      <axsl:otherwise>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="errorCode">7876</axsl:variable>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="defaultMessage">The [DATESCHEMECEASED] must be today or earlier. Please check</axsl:variable>
        <err:Error xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" xmlns:dsl="http://decisionsoft.com/rim/errorExtension">
          <err:RaisedBy>ChRIS</err:RaisedBy>
          <err:Number>
            <axsl:value-of select="normalize-space($errorCode)"/>
          </err:Number>
          <err:Type>business</err:Type>
          <err:Text>
            <axsl:choose>
              <axsl:when test="normalize-space($defaultMessage)">
                <axsl:copy-of select="$defaultMessage"/>
              </axsl:when>
              <axsl:otherwise>[DATESCHEMECEASED] must not be in the future</axsl:otherwise>
            </axsl:choose>
          </err:Text>
          <err:Location>
            <axsl:apply-templates mode="schematron-get-full-path" select="."/>
          </err:Location>
        </err:Error>
      </axsl:otherwise>
    </axsl:choose>
    <axsl:apply-templates mode="M38" select="@*|*|comment()|processing-instruction()"/>
  </axsl:template>
  <axsl:template match="text()" mode="M38" priority="-1"/>
  <axsl:template match="@*|node()" mode="M38" priority="-2">
    <axsl:apply-templates mode="M38" select="@*|node()"/>
  </axsl:template>

<!--PATTERN p35-->


	<!--RULE -->
<axsl:template match="/hd:GovTalkMessage/hd:Body/fps:IRenvelope/fps:FullPaymentSubmission/fps:FinalSubmission" mode="M39" priority="4000">

		<!--ASSERT -->
<axsl:choose>
      <axsl:when test="not ( (.) )           or             fps:BecauseSchemeCeased           or             fps:DateSchemeCeased           or             fps:ForYear"/>
      <axsl:otherwise>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="errorCode">7933</axsl:variable>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="defaultMessage">If [FINALSUBMISSION] is present then an entry in [FINALSUBMISSIONCEASEDINDICATOR], [DATESCHEMECEASED] or [FINALSUBMISSIONFORYEARINDICATOR] should be present. Please check.</axsl:variable>
        <err:Error xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" xmlns:dsl="http://decisionsoft.com/rim/errorExtension">
          <err:RaisedBy>ChRIS</err:RaisedBy>
          <err:Number>
            <axsl:value-of select="normalize-space($errorCode)"/>
          </err:Number>
          <err:Type>business</err:Type>
          <err:Text>
            <axsl:choose>
              <axsl:when test="normalize-space($defaultMessage)">
                <axsl:copy-of select="$defaultMessage"/>
              </axsl:when>
              <axsl:otherwise>If [FINALSUBMISSION] is present then [FINALSUBMISSIONCEASEDINDICATOR], [DATESCHEMECEASED] or [FINALSUBMISSIONFORYEARINDICATOR] should be present</axsl:otherwise>
            </axsl:choose>
          </err:Text>
          <err:Location>
            <axsl:apply-templates mode="schematron-get-full-path" select="."/>
          </err:Location>
        </err:Error>
      </axsl:otherwise>
    </axsl:choose>
    <axsl:apply-templates mode="M39" select="@*|*|comment()|processing-instruction()"/>
  </axsl:template>
  <axsl:template match="text()" mode="M39" priority="-1"/>
  <axsl:template match="@*|node()" mode="M39" priority="-2">
    <axsl:apply-templates mode="M39" select="@*|node()"/>
  </axsl:template>

<!--PATTERN p3-->


	<!--RULE -->
<axsl:template match="/hd:GovTalkMessage/hd:Body/fps:IRenvelope/fps:FullPaymentSubmission" mode="M40" priority="4000">

		<!--ASSERT -->
<axsl:choose>
      <axsl:when test="../../../hd:Header/hd:MessageDetails/hd:Class = 'HMRC-PAYE-RTI-FPS'           or           ../../../hd:Header/hd:MessageDetails/hd:Class = 'HMRC-PAYE-RTI-FPS-TIL'"/>
      <axsl:otherwise>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="errorCode">7837</axsl:variable>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="defaultMessage">Valid message classes for a Full Payment Submission are HMRC-PAYE-RTI-FPS and HMRC-PAYE-RTI-FPS-TIL.</axsl:variable>
        <err:Error xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" xmlns:dsl="http://decisionsoft.com/rim/errorExtension">
          <err:RaisedBy>ChRIS</err:RaisedBy>
          <err:Number>
            <axsl:value-of select="normalize-space($errorCode)"/>
          </err:Number>
          <err:Type>business</err:Type>
          <err:Text>
            <axsl:choose>
              <axsl:when test="normalize-space($defaultMessage)">
                <axsl:copy-of select="$defaultMessage"/>
              </axsl:when>
              <axsl:otherwise>Valid message classes for a Full Payment Submission are HMRC-PAYE-RTI-FPS and HMRC-PAYE-RTI-FPS-TIL.</axsl:otherwise>
            </axsl:choose>
          </err:Text>
          <err:Location>
            <axsl:apply-templates mode="schematron-get-full-path" select="."/>
          </err:Location>
        </err:Error>
      </axsl:otherwise>
    </axsl:choose>

		<!--ASSERT -->
<axsl:choose>
      <axsl:when test="fps:Employee             or           fps:CompressedPart             or           fps:FinalSubmission"/>
      <axsl:otherwise>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="errorCode">7877</axsl:variable>
        <axsl:variable xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" name="defaultMessage">At least one of [EMPLOYEE], [COMPRESSEDPART] or [FINALSUBMISSION] must be submitted</axsl:variable>
        <err:Error xmlns:err="http://www.govtalk.gov.uk/CM/errorresponse" xmlns:dsl="http://decisionsoft.com/rim/errorExtension">
          <err:RaisedBy>ChRIS</err:RaisedBy>
          <err:Number>
            <axsl:value-of select="normalize-space($errorCode)"/>
          </err:Number>
          <err:Type>business</err:Type>
          <err:Text>
            <axsl:choose>
              <axsl:when test="normalize-space($defaultMessage)">
                <axsl:copy-of select="$defaultMessage"/>
              </axsl:when>
              <axsl:otherwise>At least one of [EMPLOYEE], [COMPRESSEDPART] or [FINALSUBMISSION] must be submitted</axsl:otherwise>
            </axsl:choose>
          </err:Text>
          <err:Location>
            <axsl:apply-templates mode="schematron-get-full-path" select="."/>
          </err:Location>
        </err:Error>
      </axsl:otherwise>
    </axsl:choose>
    <axsl:apply-templates mode="M40" select="@*|*|comment()|processing-instruction()"/>
  </axsl:template>
  <axsl:template match="text()" mode="M40" priority="-1"/>
  <axsl:template match="@*|node()" mode="M40" priority="-2">
    <axsl:apply-templates mode="M40" select="@*|node()"/>
  </axsl:template>
</axsl:stylesheet>
